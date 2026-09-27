"""internal_api 包布局契约（GUIDE P2 第 5 步：单文件 → 包）。

本文件回答两个问题：

1. **对外契约不变**：拆包前后路由表、路由函数名、装配注入点、共享符必须逐条一致
   （`PKG-A*`，拆包前后都必须全绿）。
2. **拆包确实完成**：`internal_api` 是包、`__init__.py` 内无路由、子模块不写裸工厂名
   （`PKG-B*`，拆包前为红，Task 3 后转绿）。

同时向另外三个「源码扫描型」测试（`test_singleton_assembly_contract` /
`test_error_fallback_contract` / `test_sse_shared_facilities_delegation`）提供
一个**布局无关**的源码解析器（`internal_api_sources` / `internal_api_source_text` /
`ai_service_dir`），使它们从「扫单文件」升级为「扫包内全文件」，断言强度不变。
"""

import ast
import inspect
from pathlib import Path

import internal_api


# ═══════════════════════════════════════════════════════════════════
# 布局无关的源码解析器（多个测试文件复用）
# ═══════════════════════════════════════════════════════════════════


def internal_api_sources() -> list[Path]:
    """`internal_api` 的生产源码文件列表。

    - 拆包前：`internal_api` 是单文件 → 返回该文件；
    - 拆包后：`internal_api` 是包 → 返回包内全部 `.py`。

    这样调用方（源码/结构断言）无需知道当前是哪种布局。
    """
    mod_path = Path(internal_api.__file__).resolve()
    if mod_path.name == "__init__.py":
        return sorted(mod_path.parent.glob("*.py"))
    return [mod_path]


def internal_api_source_text() -> str:
    """所有生产源码的拼接文本（仅用于 `in` / 正则类断言）。"""
    return "\n\n".join(p.read_text(encoding="utf-8") for p in internal_api_sources())


def ai_service_dir() -> Path:
    """`ai-service` 目录（拆包后是包的上一级）。"""
    mod_path = Path(internal_api.__file__).resolve()
    return mod_path.parent.parent if mod_path.name == "__init__.py" else mod_path.parent


# ═══════════════════════════════════════════════════════════════════
# 拆包前抄下来的对外契约（golden）
# ═══════════════════════════════════════════════════════════════════

# 49 条路由：(方法, 完整路径)。拆包不得增删任何一条。
# P2 Task 2 有意扩展一次：+ `POST /internal/evidence/apply`（`LearningEvidence` 记账）。
GOLDEN_ROUTES = frozenset({
    ("POST", "/internal/profile/chat"),
    ("POST", "/internal/profile/workflow/status"),
    ("POST", "/internal/resources/generate"),
    ("POST", "/internal/resources/export-pptx"),
    ("GET", "/internal/resources/download-pptx"),
    ("POST", "/internal/resources/export-docx"),
    ("GET", "/internal/resources/download-docx"),
    ("POST", "/internal/resources/export-pdf"),
    ("GET", "/internal/resources/download-pdf"),
    ("POST", "/internal/tutor/chat"),
    ("POST", "/internal/path/{student_id}"),
    ("POST", "/internal/conversations/{conversation_id}/summary"),
    ("POST", "/internal/api/chat"),
    ("POST", "/internal/exercise/generate"),
    ("POST", "/internal/solve"),
    ("POST", "/internal/exercise/error-analysis"),
    ("POST", "/internal/exercise/grade"),
    ("POST", "/internal/evaluation/report"),
    ("POST", "/internal/exercise/categorize"),
    ("POST", "/internal/exercise/session/analyze"),
    ("POST", "/internal/exercise/dashboard"),
    ("POST", "/internal/exercise/profile/enrich"),
    ("POST", "/internal/knowledge-graph/{course_id}"),
    ("POST", "/internal/knowledge-graph/{course_id}/node/{node_id}"),
    ("POST", "/internal/graph/extract"),
    ("POST", "/internal/graph/nodes"),
    ("POST", "/internal/graph/masteries"),
    ("POST", "/internal/graph/reload"),
    ("POST", "/internal/graph/next-node"),
    ("POST", "/internal/graph/progress"),
    ("POST", "/internal/graph/check-prerequisites"),
    ("POST", "/internal/graph/nodes/{node_id}/delete"),
    ("POST", "/internal/graph/nodes/{node_id}/update"),
    ("POST", "/internal/graph/suggest-edges"),
    ("POST", "/internal/graph/export-mermaid"),
    ("POST", "/internal/graph/layered"),
    ("POST", "/internal/plans/create-from-path"),
    ("POST", "/internal/plans/{plan_id}/complete-step"),
    ("POST", "/internal/plans/{plan_id}/today"),
    ("POST", "/internal/plans/{plan_id}/progress"),
    ("POST", "/internal/plans/{plan_id}/node-status-change"),
    ("POST", "/internal/plans/{plan_id}/status"),
    ("POST", "/internal/plans/status"),
    ("POST", "/internal/plans/{plan_id}/regression-check"),
    ("POST", "/internal/plans/{plan_id}/review-schedule"),
    ("POST", "/internal/inquiry/resolve"),
    ("POST", "/internal/inquiry/resolve/plan"),
    ("POST", "/internal/eval/judge"),
    ("POST", "/internal/evidence/apply"),
})

# 路由处理函数名（49 个装饰器 + `_unified_chat` 实现，共 50）。
# 既有测试用 `getattr(internal_api, name)` / `inspect.getsource(...)` 引用它们，
# 拆包后必须仍是包属性。
ROUTE_FUNCTIONS = [
    "profile_chat", "profile_workflow_status",
    "resources_generate", "export_pptx", "download_pptx",
    "export_docx", "download_docx", "export_pdf", "download_pdf",
    "tutor_chat", "learning_path", "get_conversation_summary",
    "unified_chat", "_unified_chat",
    "exercise_generate", "solve_question", "exercise_error_analysis",
    "grade_exercise", "get_evaluation_report", "categorize_exercises",
    "analyze_session", "exercise_dashboard", "enrich_profile",
    "get_knowledge_graph", "get_node_card", "graph_extract", "graph_nodes",
    "update_masteries", "reload_graph", "recommend_next_node",
    "get_progress_summary", "check_prerequisites", "delete_node",
    "update_node", "suggest_edges", "export_mermaid", "get_layered_graph",
    "create_plan_from_path", "complete_plan_step", "get_today_tasks",
    "update_plan_progress", "on_node_status_change", "get_plan_status",
    "get_plan_status_legacy", "regression_check", "get_review_schedule",
    "inquiry_resolve", "inquiry_resolve_plan", "eval_judge",
    "apply_learning_evidence",
]

# 18 个惰性单例工厂 → 状态变量名（与 test_singleton_assembly_contract 同源）。
LAZY_FACTORIES = [
    "_get_chat_center", "_get_profile_agent", "_get_tutor_agent",
    "_get_tutor_center", "_get_content_agent", "_get_exercise_agent",
    "_get_exercise_center", "_get_path_agent", "_get_mindmap_agent",
    "_get_code_agent", "_get_profile_workflow", "_get_resource_center",
    "_get_path_workflow", "_get_inquiry_service", "_get_plan_center",
    "_get_graph_service", "_get_graph_center", "_get_intent_extractor",
]

SINGLETON_OF = {
    "_get_chat_center": "_chat_center_singleton",
    "_get_profile_agent": "_profile_agent_singleton",
    "_get_tutor_agent": "_tutor_agent_singleton",
    "_get_tutor_center": "_tutor_center_singleton",
    "_get_content_agent": "_content_agent_singleton",
    "_get_exercise_agent": "_exercise_agent_singleton",
    "_get_exercise_center": "_exercise_center_singleton",
    "_get_path_agent": "_path_agent_singleton",
    "_get_mindmap_agent": "_mindmap_agent_singleton",
    "_get_code_agent": "_code_agent_singleton",
    "_get_profile_workflow": "_profile_workflow_singleton",
    "_get_resource_center": "_resource_center_singleton",
    "_get_path_workflow": "_path_workflow_singleton",
    "_get_inquiry_service": "_inquiry_service_singleton",
    "_get_plan_center": "_plan_center_singleton",
    "_get_graph_service": "_graph_service_singleton",
    "_get_graph_center": "_graph_center_singleton",
    "_get_intent_extractor": "_intent_extractor",
}

# 拆包后应存在的域模块（不含 `__init__.py`）。
DOMAIN_MODULES = [
    "profile", "resources", "tutor", "chat", "exercise",
    "graph", "plans", "inquiry", "eval_api", "evidence", "_helpers",
]

# 子模块内必须以 `api.` 限定访问的可注入名（裸名会导致注入点静默失效）。
# `api_success` / `api_error` 由 `_boom_success()`（图谱/计划契约测试）直接 patch。
MUST_BE_PACKAGE_QUALIFIED_NAMES = {
    "sse_response",
    "safe_export_path",
    "api_success",
    "api_error",
    "_EXPORTS_DIR",
}

# 被测试 patch 的额外模块级名（非工厂）。
EXTRA_PATCHABLE = ["_get_mock_flag", "_EXPORTS_DIR", "_sse_stream_chunks"]

# 注入点/spy 依赖的共享符（spy 通过 monkeypatch.setattr(internal_api, ...) 生效）。
SHARED_SYMBOLS = [
    "sse_response", "safe_export_path", "sanitize_model",
    "done_event", "error_content_event",
    "api_error", "api_success", "ErrorCode",
    "router",
]


def _route_table() -> set[tuple[str, str]]:
    table: set[tuple[str, str]] = set()
    for route in internal_api.router.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            table.add((method, route.path))
    return table


# ═══════════════════════════════════════════════════════════════════
# Part A —— 对外契约（拆包前后都必须全绿）
# ═══════════════════════════════════════════════════════════════════


class TestPackageContractSurface:

    def test_pkg_a01_router_prefix_is_frozen(self):
        assert internal_api.router.prefix == "/internal"

    def test_pkg_a02_route_table_is_frozen(self):
        assert _route_table() == GOLDEN_ROUTES

    def test_pkg_a03_route_functions_are_package_attributes(self):
        missing = [n for n in ROUTE_FUNCTIONS if not callable(getattr(internal_api, n, None))]
        assert missing == [], f"路由函数不再是包属性：{missing}"

    def test_pkg_a04_route_functions_have_source_and_decorator(self):
        for name in ROUTE_FUNCTIONS:
            source = inspect.getsource(getattr(internal_api, name))
            # `_unified_chat` 是实现体（无装饰器），其余路由必须仍带 router 装饰器。
            if name != "_unified_chat":
                assert "router." in source, f"{name} 丢失路由装饰器"

    def test_pkg_a05_assembly_surface_is_package_attributes(self):
        expected = (
            LAZY_FACTORIES
            + list(SINGLETON_OF.values())
            + [f"_{n[len('_get_'):]}_lock" for n in LAZY_FACTORIES]
            + EXTRA_PATCHABLE
        )
        missing = [n for n in expected if not hasattr(internal_api, n)]
        assert missing == [], f"装配注入点不再是包属性：{missing}"

    def test_pkg_a06_shared_symbols_are_package_attributes(self):
        missing = [n for n in SHARED_SYMBOLS if not hasattr(internal_api, n)]
        assert missing == [], f"共享符不再是包属性：{missing}"

    def test_pkg_a07_openapi_paths_match_golden(self):
        """以 FastAPI 实际注册结果为准，再验一次（防 `router.routes` 与挂载不一致）。"""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(internal_api.router)
        registered = set()
        for path, operations in app.openapi()["paths"].items():
            for method in operations:
                if method.upper() in ("HEAD", "OPTIONS"):
                    continue
                registered.add((method.upper(), path))
        assert registered == GOLDEN_ROUTES


# ═══════════════════════════════════════════════════════════════════
# Part B —— 拆包完成度（拆包前为红，Task 3 后转绿）
# ═══════════════════════════════════════════════════════════════════


class TestPackageLayout:

    def test_pkg_b01_internal_api_is_a_package(self):
        assert Path(internal_api.__file__).name == "__init__.py", (
            f"internal_api 仍是单文件：{internal_api.__file__}"
        )

    def test_pkg_b02_domain_modules_exist(self):
        package_dir = Path(internal_api.__file__).resolve().parent
        missing = [m for m in DOMAIN_MODULES if not (package_dir / f"{m}.py").exists()]
        assert missing == [], f"域模块缺失：{missing}"

    def test_pkg_b03_init_has_no_route_functions(self):
        """`__init__.py` 应是薄壳（装配 + 聚合 + re-export），不含路由实现。"""
        package_dir = Path(internal_api.__file__).resolve().parent
        init_path = package_dir / "__init__.py"
        if not init_path.exists():
            return  # 拆包前：`internal_api` 还不是包，交由 PKG-B01 报红
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        route_fns = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any("router." in ast.unparse(d) for d in node.decorator_list):
                route_fns.append(node.name)
        assert route_fns == [], f"路由函数仍留在 __init__.py：{route_fns}"

    def test_pkg_b04_submodules_avoid_bare_patchable_names(self):
        """子模块内禁止裸 `_get_xxx()` / `sse_response()` / `safe_export_path()` / `_EXPORTS_DIR`。

        裸名会绑到子模块自己的全局，`monkeypatch.setattr(internal_api, ...)` 将静默失效。
        这是本次拆包**最隐蔽**的风险，故钉成结构断言。

        判定口径：裸名**同时也是 `internal_api` 包的属性**才算隐患（局部别名如
        `from app.services.llm_service import get_llm_service as _get_llm` 不算）。
        """
        package_dir = Path(internal_api.__file__).resolve().parent
        if not (package_dir / "__init__.py").exists():
            return  # 拆包前：无子模块，跳过（空过）

        package_names = set(dir(internal_api))
        offenders: list[str] = []
        for path in sorted(package_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    name = node.func.id
                    if name in package_names and (
                        name.startswith("_get_") or name in MUST_BE_PACKAGE_QUALIFIED_NAMES
                    ):
                        offenders.append(f"{path.name}:{node.lineno} {name}()")
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id == "_EXPORTS_DIR" and node.id in package_names:
                        offenders.append(f"{path.name}:{node.lineno} _EXPORTS_DIR")
        assert offenders == [], f"子模块出现裸的可注入名（须写 api.xxx）：{offenders}"
