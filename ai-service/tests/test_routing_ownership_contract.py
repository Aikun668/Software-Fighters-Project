"""GUIDE P3-A：决策所有权 / 分层边界 / 约定标注 的契约锁定。

本文件把《三类决策与命名约定》钉成**可执行事实**，回答 GUIDE P3 的验收问题：
「谁负责路由、谁负责编排、谁负责执行、谁负责状态」，不需要靠猜。

三部分：

- **Part A（`RO-A01..A05`）**：三类决策（五处实现）的**引用唯一性**（import 级）。
  一旦将来"又长出一套路由"，本组会先红。
- **Part B（`RO-A06..A07`）**：分层边界 —— API 层不得引用路由决策符号；
  Center 层不得 import 资源选择器（防「资源 Agent 选择」升格为全局路由器）。
- **Part C（`RO-A08..A09`）**：约定标注存在于 docstring（防"标注被删 → 文档与代码漂移"）。

⚠️ **本文件不改动任何生产行为**。
Part C 在 Task 1 时为红（标注尚未添加），Task 2 加标注后转绿；Part A/B 全程绿。
"""

import ast
from pathlib import Path

import pytest

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = AI_SERVICE_DIR / "app"
INTERNAL_API_DIR = AI_SERVICE_DIR / "internal_api"


# ═══════════════════════════════════════════════════════════════════
# 契约数据
# ═══════════════════════════════════════════════════════════════════

# 三类决策 / 五处实现：被引用模块 → 允许引用它的生产文件（posix 相对路径）。
# 依据诊断：每处决策都有唯一调用点；此表即"所有权"的可执行形式。
DECISION_MODULE_OWNERS = {
    # 一级能力守门（是否明确要求专项产物）
    "app.services.capability_gate": {"app/centers/chat_center.py"},
    # 二级意图分发（进哪个业务域）
    "app.centers.router_agent": {"app/centers/chat_center.py"},
    # 三态语义路由（T4-A：明确聊天/明确能力/不确定的边界裁决）
    "app.services.semantic_router": {"app/centers/chat_center.py"},
    # 内容领域分类（AI / 通用）—— 纯分类，不参与执行单元选择
    "app.services.domain_classifier": {"app/agents/tutor_agent.py"},
    # 资源流内部的专项 Agent 选择
    "app.orchestration.resource_selector": {
        "app/workflows/resource_gen.py",
        "app/orchestration/__init__.py",
    },
}

# API 层禁止**引用**的路由决策符号（AST 级；docstring 里的文字说明不算引用）。
API_FORBIDDEN_SYMBOLS = {
    "RouterAgent",
    "ChatTaskDispatcher",     # 原 ResultAgent（P3-B3a 改名）
    "CapabilityGate",
    "ResourceAgentSelector",  # 原 Director（P3-B2 改名）
    "DomainClassifier",       # 原 DomainRouter（P3-B2 改名）
    # 旧名一并保留为「不得复活」护栏
    "ResultAgent",
    "Director",
    "DomainRouter",
}

# 约定标注（由 Task 2 写入各模块 docstring）
OWNERSHIP_MARKER = "【决策所有权】"
NAMING_MARKER = "【命名澄清】"

# 五处决策实现的落点
OWNERSHIP_MODULES = [
    "app/services/capability_gate.py",
    "app/centers/router_agent.py",
    "app/services/intent_extractor.py",
    "app/services/domain_classifier.py",
    "app/orchestration/resource_selector.py",
]

# 名字与实际职责不符的落点（改名排在 P3-B，P3-A 只做澄清标注）
#   ⚠️ `resource_whiteboard.py` 的路径在 P3-B1 随"移出 workflows/"计划迁移
#   （`app/workflows/` → `app/orchestration/`），标注随文件走；迁移由 `RO-D04` 锁定。
NAMING_MODULES = [
    "app/centers/router_agent.py",
    "app/centers/chat_task_dispatcher.py",  # P3-B3a：原 result_agent.py
    "app/centers/auto_center.py",
    "app/services/domain_classifier.py",
    "app/orchestration/resource_selector.py",
    "app/workflows/profile_workflow.py",
    "app/orchestration/resource_whiteboard.py",
]


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════


def _iter_app_py() -> list[Path]:
    return sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    """该文件 import 的**绝对**模块名（`from X import ...` 与 `import X.Y`）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import：本仓 app/** 不用，保险跳过
                continue
            if node.module:
                modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
    return modules


def _matches(modules: set[str], target: str) -> bool:
    return any(m == target or m.startswith(target + ".") for m in modules)


def _referencing_files(target_module: str) -> set[str]:
    hits: set[str] = set()
    for path in _iter_app_py():
        if _matches(_imported_modules(path), target_module):
            hits.add(path.relative_to(AI_SERVICE_DIR).as_posix())
    return hits


# ═══════════════════════════════════════════════════════════════════
# Part A —— 决策所有权（引用唯一性）
# ═══════════════════════════════════════════════════════════════════


class TestDecisionOwnership:

    @pytest.mark.parametrize(
        "target_module,expected",
        sorted(DECISION_MODULE_OWNERS.items()),
        ids=[m.split(".")[-1] for m, _ in sorted(DECISION_MODULE_OWNERS.items())],
    )
    def test_ro_a01_a04_decision_module_has_exactly_these_referrers(
        self, target_module, expected,
    ):
        """每处决策模块的引用者集合必须与约定完全一致（多一个 = 新旁路，少一个 = 删过头）。"""
        actual = _referencing_files(target_module)
        assert actual == expected, (
            f"{target_module} 的引用者与约定不符\n"
            f"  约定：{sorted(expected)}\n"
            f"  实际：{sorted(actual)}"
        )

    def test_ro_a05_api_layer_does_not_import_decision_modules(self):
        """API 层（`internal_api/` 包）不得 import 任何路由决策模块。"""
        offenders: list[str] = []
        for path in sorted(INTERNAL_API_DIR.glob("*.py")):
            modules = _imported_modules(path)
            for target in DECISION_MODULE_OWNERS:
                if _matches(modules, target):
                    offenders.append(f"{path.name} → {target}")
        assert offenders == [], f"API 层直连路由决策模块：{offenders}"


# ═══════════════════════════════════════════════════════════════════
# Part B —— 分层边界
# ═══════════════════════════════════════════════════════════════════


class TestLayerBoundaries:

    @staticmethod
    def _symbol_references(path: Path) -> list[str]:
        """返回文件内对禁用符号的**代码级**引用（docstring 文本不算）。"""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in API_FORBIDDEN_SYMBOLS:
                hits.append(f"{path.name}:{node.lineno} Name:{node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in API_FORBIDDEN_SYMBOLS:
                hits.append(f"{path.name}:{node.lineno} Attr:{node.attr}")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    short = alias.name.split(".")[-1]
                    if short in API_FORBIDDEN_SYMBOLS:
                        hits.append(f"{path.name}:{node.lineno} import:{alias.name}")
        return hits

    def test_ro_a06_api_layer_does_not_reference_routing_symbols(self):
        """API 层不得**引用**路由决策符号（字面串出现在 docstring 说明里是允许的）。

        这是 `test_chat_center_api_delegation.py:266-277` 的**全包版**：
        那边只锁 `_unified_chat` 一个函数的源码文本，这边覆盖整个 `internal_api/`。
        """
        offenders: list[str] = []
        for path in sorted(INTERNAL_API_DIR.glob("*.py")):
            offenders.extend(self._symbol_references(path))
        assert offenders == [], f"API 层引用了路由决策符号：{offenders}"

    def test_ro_a07_centers_do_not_import_resource_director(self):
        """`app/centers/**` 不得 import 资源选择器。

        `ResourceAgentSelector`（原 `Director`）的作用域**仅限资源工作流内部**
        （`AI_SERVICE_ARCHITECTURE_ISSUES.md`：「Director 只允许在资源工作流内部选择资源 Agent，
        不能成为全局请求路由器」）。
        """
        offenders: list[str] = []
        centers_dir = APP_DIR / "centers"
        for path in sorted(centers_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if _matches(_imported_modules(path), "app.orchestration.resource_selector"):
                offenders.append(path.relative_to(AI_SERVICE_DIR).as_posix())
        assert offenders == [], f"Center 层 import 了资源选择器：{offenders}"


# ═══════════════════════════════════════════════════════════════════
# Part C —— 约定标注（Task 1 红 → Task 2 绿）
# ═══════════════════════════════════════════════════════════════════


class TestConventionAnnotations:
    """标注是"文档 ↔ 代码"的锚点：删掉标注会让本组先红，提醒同步修订约定文档。"""

    @pytest.mark.parametrize("relative", OWNERSHIP_MODULES)
    def test_ro_a08_ownership_marker_present(self, relative):
        source = (AI_SERVICE_DIR / relative).read_text(encoding="utf-8")
        assert OWNERSHIP_MARKER in source, (
            f"{relative} 缺少 {OWNERSHIP_MARKER} 标注（决策所有权说明被删或未加）"
        )

    @pytest.mark.parametrize("relative", NAMING_MODULES)
    def test_ro_a09_naming_marker_present(self, relative):
        source = (AI_SERVICE_DIR / relative).read_text(encoding="utf-8")
        assert NAMING_MARKER in source, (
            f"{relative} 缺少 {NAMING_MARKER} 标注（命名澄清说明被删或未加）"
        )


# ═══════════════════════════════════════════════════════════════════
# Part D —— P3-B1 结构收敛（Task 1 红 → Task 2/3/4 绿）
# ═══════════════════════════════════════════════════════════════════

ROUTER_AGENT_FILE = "app/centers/router_agent.py"
PROFILE_WORKFLOW_FILE = "app/workflows/profile_workflow.py"

# `RouterAgent` 内的死代码（零引用，确认后删除）
ROUTER_AGENT_DEAD_MARKERS = ["_use_llm", "_intents_to_tasks", "self.intent_extractor"]

# `profile_workflow` 的 `director` 旧标识（改名后不得残留）
PROFILE_WORKFLOW_OLD_MARKERS = [
    "_director_node",
    "_route_after_director",
    'add_node("director"',
]
PROFILE_WORKFLOW_NEW_NODE = '"completeness_check"'

# `ResourceWhiteboard` 归位：旧位置消失、新位置存在
WHITEBOARD_OLD_PATH = "app/workflows/resource_whiteboard.py"
WHITEBOARD_NEW_PATH = "app/orchestration/resource_whiteboard.py"


class TestP3B1Structure:

    def test_ro_d01_router_agent_dead_code_removed(self):
        """`_use_llm` / `_intents_to_tasks` / `self.intent_extractor` 三处死代码应已删除。

        ⚠️ 构造参数 `intent_extractor=` **保留**（10 个测试文件传参，属测试契约）。
        """
        source = (AI_SERVICE_DIR / ROUTER_AGENT_FILE).read_text(encoding="utf-8")
        offenders = [m for m in ROUTER_AGENT_DEAD_MARKERS if m in source]
        assert offenders == [], f"RouterAgent 仍有死代码：{offenders}"

    def test_ro_d02_router_agent_no_longer_imports_os(self):
        """`import os` 原本只被 `_use_llm` 使用；死代码删除后应一并移除。"""
        path = AI_SERVICE_DIR / ROUTER_AGENT_FILE
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert "os" not in imported, "router_agent 仍 import os（已无使用者）"

    def test_ro_d03_profile_workflow_director_node_renamed(self):
        """`director` 图节点改名 `completeness_check`（字符串 + 两个函数名）。"""
        source = (AI_SERVICE_DIR / PROFILE_WORKFLOW_FILE).read_text(encoding="utf-8")
        assert PROFILE_WORKFLOW_NEW_NODE in source, "未注册 completeness_check 节点"
        leftovers = [m for m in PROFILE_WORKFLOW_OLD_MARKERS if m in source]
        assert leftovers == [], f"旧 director 标识残留：{leftovers}"

    def test_ro_d04_resource_whiteboard_moved_out_of_workflows(self):
        """`ResourceWhiteboard` 不是 Workflow，应移出 `app/workflows/`。"""
        old = AI_SERVICE_DIR / WHITEBOARD_OLD_PATH
        new = AI_SERVICE_DIR / WHITEBOARD_NEW_PATH
        assert not old.exists(), f"{WHITEBOARD_OLD_PATH} 仍存在（未归位）"
        assert new.exists(), f"{WHITEBOARD_NEW_PATH} 不存在（未归位）"

    def test_ro_d05_router_agent_still_accepts_intent_extractor_param(self):
        """防"删死代码删过头"：构造参数 `intent_extractor` 必须仍在。"""
        source = (AI_SERVICE_DIR / ROUTER_AGENT_FILE).read_text(encoding="utf-8")
        assert "intent_extractor: IntentExtractor | None" in source, (
            "RouterAgent 构造参数被误删（10 个测试文件依赖它）"
        )


# ═══════════════════════════════════════════════════════════════════
# Part E —— P3-B2 重命名（Task 1 红 → 改名后绿）
# ═══════════════════════════════════════════════════════════════════

B4_OLD_MODULE = "app/orchestration/director.py"
B4_NEW_MODULE = "app/orchestration/resource_selector.py"
B4_OLD_SYMBOL = "Director"
B4_NEW_SYMBOL = "ResourceAgentSelector"

B5_OLD_MODULE = "app/services/domain_router.py"
B5_NEW_MODULE = "app/services/domain_classifier.py"
B5_OLD_SYMBOL = "DomainRouter"
B5_NEW_SYMBOL = "DomainClassifier"


def _production_and_test_sources() -> list[Path]:
    """`app/**` 与 `tests/**` 下的全部 `.py`（用于"旧名零残留"扫描）。

    ⚠️ 排除**本文件自身**：它必须保留旧名作为"不得复活"的期望值，
    否则扫描会自我指涉（RO-E02 曾因此误报）。
    """
    self_path = Path(__file__).resolve()
    roots = [APP_DIR, AI_SERVICE_DIR / "tests"]
    out: list[Path] = []
    for root in roots:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or path.resolve() == self_path:
                continue
            out.append(path)
    return sorted(out)


class TestP3B2Renames:

    @pytest.mark.parametrize(
        "old,new,new_symbol",
        [
            (B4_OLD_MODULE, B4_NEW_MODULE, B4_NEW_SYMBOL),
            (B5_OLD_MODULE, B5_NEW_MODULE, B5_NEW_SYMBOL),
        ],
        ids=["director", "domain_router"],
    )
    def test_ro_e01_module_file_renamed(self, old, new, new_symbol):
        assert not (AI_SERVICE_DIR / old).exists(), f"{old} 仍存在（模块未改名）"
        new_path = AI_SERVICE_DIR / new
        assert new_path.exists(), f"{new} 不存在"
        assert f"class {new_symbol}" in new_path.read_text(encoding="utf-8"), (
            f"{new} 未定义 class {new_symbol}"
        )

    @pytest.mark.parametrize(
        "old_text",
        [
            "app.orchestration.director",
            "app.services.domain_router",
            "from app.orchestration.director",
            "from app.services.domain_router",
        ],
    )
    def test_ro_e02_no_importer_left_on_old_module_path(self, old_text):
        offenders: list[str] = []
        for path in _production_and_test_sources():
            if old_text in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(AI_SERVICE_DIR).as_posix())
        assert offenders == [], f"仍引用旧模块路径 `{old_text}`：{offenders}"

    @pytest.mark.parametrize(
        "old_symbol",
        [B4_OLD_SYMBOL, B5_OLD_SYMBOL, "get_domain_router", "_get_domain_router"],
    )
    def test_ro_e03_old_symbols_have_no_code_references(self, old_symbol):
        """旧符号名不得再作为 **代码** 出现（docstring 里的历史说明不算）。

        判定：该类名/函数名出现且同行同时含 `class ` / `def ` / `import ` / `(` 调用形态。
        更稳的判定放在 `RO-E01`（新名已定义）与 `RO-E02`（旧模块路径零引用）上；
        本用例只挡"`Director(` / `DomainRouter(` 之类的新代码引用"。
        """
        offenders: list[str] = []
        for path in _production_and_test_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == old_symbol:
                    offenders.append(f"{path.name}:{node.lineno} Name:{old_symbol}")
                elif isinstance(node, ast.Attribute) and node.attr == old_symbol:
                    offenders.append(f"{path.name}:{node.lineno} Attr:{old_symbol}")
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.name.split(".")[-1] == old_symbol:
                            offenders.append(
                                f"{path.name}:{node.lineno} import:{alias.name}"
                            )
        assert offenders == [], f"旧符号 {old_symbol} 仍被代码引用：{offenders}"

    def test_ro_e04_resource_gen_no_longer_uses_director_attribute(self):
        """`ResourceGenWorkflow` 的实例属性同步改名（`director` → `selector`）。"""
        source = (AI_SERVICE_DIR / "app/workflows/resource_gen.py").read_text(encoding="utf-8")
        assert "self.director" not in source, "ResourceGenWorkflow.director 属性残留"
        assert "self.selector" in source, "ResourceGenWorkflow.selector 属性缺失"
