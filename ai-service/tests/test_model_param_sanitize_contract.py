"""模型参数清洗契约（GUIDE P2 第 3 步收尾，P3-D 轮）。

## 「模型参数清洗」在本项目里到底是什么

GUIDE 原文（P2 第 3 步）：`抽出多模态消息构建与解析、安全校验、模型参数清洗等纯能力模块`。

摸清后它由两件事构成，本文件把两件都钉住：

1. **送入模型的文本要清洗** —— `app/utils/prompt_guard.py::sanitize_model()`
   （递归清洗 Pydantic 模型/dict/list 里的所有 str 字段：截断到 4000 字 + 过滤 8 类
   prompt 注入模式。**就是**「模型参数清洗」在本项目里的落地形态）
2. **客户端不得指定模型参数**（model / temperature / max_tokens …）—— 本项目
   **根本没有**这类请求字段，故用不变量锁死，防止以后被加进来。

## 为什么要锁

在此之前 `sanitize_model` 只覆盖 8 个路由，而 **`/graph/extract`、`/plans/create-from-path`、
`/plans/{id}/complete-step` 这三个入口的自由文本是直通 LLM 的、完全没清洗**（本轮补齐）。

| 编号 | 断言 |
|---|---|
| `MS-A01` | 新增的 3 个 LLM 边界入口必须调用 `sanitize_model` |
| `MS-A02` | 全仓 `internal_api/**` 的清洗调用点不少于 11 处（防退化） |
| `MS-A03` | `/eval/judge` **不得**清洗 —— 理由见用例 docstring |
| `MS-B01` | 请求模型不得暴露任何模型参数字段 |
| `MS-C01..C03` | `_get_mock_flag()` 环境化：默认 False（零行为变化）、env 可开、仍可 patch |
"""

import ast
import importlib
import inspect
from pathlib import Path

import pytest

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
INTERNAL_API_DIR = AI_SERVICE_DIR / "internal_api"
MODELS_PATH = AI_SERVICE_DIR / "app/api/models.py"

# 客户端不得指定的模型参数字段名（本仓库当前一个都没有）
FORBIDDEN_PARAM_FIELDS = {
    "model", "model_name", "temperature", "top_p", "max_tokens", "max_output_tokens",
    "api_key", "base_url", "thinking", "thinking_enabled", "provider", "endpoint",
}

# 本轮新接线的 LLM 边界入口：模块 → 路由函数名
NEWLY_WIRED = {
    "graph.py": ["graph_extract"],
    "plans.py": ["create_plan_from_path", "complete_plan_step"],
}


def _module_ast(filename: str) -> ast.Module:
    return ast.parse((INTERNAL_API_DIR / filename).read_text(encoding="utf-8"))


def _calls_sanitize(func: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """函数体内是否出现 `sanitize_model(...)` 调用。"""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            func_node = node.func
            if isinstance(func_node, ast.Name) and func_node.id == "sanitize_model":
                return True
            if isinstance(func_node, ast.Attribute) and func_node.attr == "sanitize_model":
                return True
    return False


def _find_function(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ═══════════════════════════════════════════════════════════════════
# Part A —— 清洗覆盖面
# ═══════════════════════════════════════════════════════════════════


class TestSanitizeCoverage:

    @pytest.mark.parametrize(
        "filename,func_name",
        [(f, n) for f, names in NEWLY_WIRED.items() for n in names],
    )
    def test_ms_a01_newly_wired_entries_call_sanitize(self, filename, func_name):
        """这三个入口的自由文本直通 LLM，必须清洗。"""
        func = _find_function(_module_ast(filename), func_name)
        assert func is not None, f"{filename} 找不到路由函数 {func_name}"
        assert _calls_sanitize(func), (
            f"{filename}::{func_name} 没有调用 sanitize_model —— 用户文本会裸奔进 LLM"
        )

    def test_ms_a02_total_call_sites_do_not_regress(self):
        """全仓 `internal_api/**` 的清洗调用点总数不得少于 11（8 旧 + 3 新）。"""
        total = 0
        for path in INTERNAL_API_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id == "sanitize_model":
                    total += 1
        assert total >= 11, f"清洗调用点减少到 {total} 处（应 ≥ 11）"

    def test_ms_a03_eval_judge_must_stay_unsanitized(self):
        """`/eval/judge` **不得**清洗 —— 它是评测旁路通道。

        它的用途就是「把（可能含恶意/注入文本的）材料直接丢给 LLM 做裁判」，
        清洗会把待评审内容里的注入样本一起洗掉，**评测能力被洗没**。
        该路由只服务自动化测试，非用户链路，故按设计豁免。
        """
        func = _find_function(_module_ast("eval_api.py"), "eval_judge")
        assert func is not None, "eval_api.py 找不到 eval_judge"
        assert not _calls_sanitize(func), (
            "eval_judge 被接上了 sanitize_model —— 会削弱评测能力，请先改本用例的定性"
        )


# ═══════════════════════════════════════════════════════════════════
# Part B —— 客户端不得指定模型参数
# ═══════════════════════════════════════════════════════════════════


def _request_field_names(path: Path) -> list[tuple[str, str]]:
    """(模型类名, 字段名) 列表。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        bases = {ast.unparse(b) for b in cls.bases}
        if not any("BaseModel" in b for b in bases):
            continue
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                found.append((cls.name, stmt.target.id))
    return found


class TestNoClientModelParams:

    def test_ms_b01_no_request_model_exposes_model_params(self):
        """请求模型里不得出现任何模型参数字段（本项目当前就是零）。"""
        paths = [MODELS_PATH, INTERNAL_API_DIR / "eval_api.py"]
        offenders: list[str] = []
        for path in paths:
            for cls_name, field in _request_field_names(path):
                if field.lower() in FORBIDDEN_PARAM_FIELDS:
                    offenders.append(f"{path.name}:{cls_name}.{field}")
        assert offenders == [], (
            "请求模型暴露了模型参数（客户端可影响模型选择/采样）：\n" + "\n".join(offenders)
        )


# ═══════════════════════════════════════════════════════════════════
# Part C —— `_get_mock_flag()` 环境化
# ═══════════════════════════════════════════════════════════════════


class TestMockFlagIsEnvDriven:

    def test_ms_c01_default_is_false(self, monkeypatch):
        """未设置环境变量 → False（生产默认，与历史硬编码逐字一致）。"""
        monkeypatch.delenv("AI_SERVICE_MOCK_LLM", raising=False)
        internal_api = importlib.import_module("internal_api")
        assert internal_api._get_mock_flag() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_ms_c02_env_can_enable_mock(self, monkeypatch, value):
        monkeypatch.setenv("AI_SERVICE_MOCK_LLM", value)
        internal_api = importlib.import_module("internal_api")
        assert internal_api._get_mock_flag() is True

    def test_ms_c03_remains_patchable_in_package_namespace(self, monkeypatch):
        """旧手法（patch `internal_api._get_mock_flag`）必须继续有效。"""
        internal_api = importlib.import_module("internal_api")
        monkeypatch.setattr(internal_api, "_get_mock_flag", lambda: True)
        assert internal_api._get_mock_flag() is True
        # 仍是本包命名空间下的函数（拆包后 18 个工厂依赖这一点）
        import internal_api as pkg

        assert inspect.isfunction(pkg._get_mock_flag)
