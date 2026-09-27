"""Mock/模型配置开关口径契约（学习闭环化 P0-B 轮）。

## 为什么单独一份契约

`AI_SERVICE_MOCK_LLM`（`internal_api._get_mock_flag()` 读）目前只覆盖 12 个
`_get_xxx` 工厂。**四条路径不认它**：

1. 聊天主链路 —— `internal_api._get_chat_center()` → `ChatCenter()` →
   `_get_dispatcher()` 直连 8 Agent + 5 Center，**无一传 mock 旗标**；
2. 会话摘要 —— `app/utils/conversation_compress.py` 两处 `create_llm(...)` 不传 `use_mock`；
3. 各 Center 惰性默认构造 —— `AutoCenter` / `ExerciseCenter` / `TutorCenter` /
   `VisualizationCenter` 的 `XxxAgent()` 无参调用；
4. provider 的 thinking 降级 fallback —— `llm_service.py:666/795`。

且**结构性障碍**：Center 层 8 个全部没有 mock 形参，`AdjustmentAgent` /
`DiagnoseAgent` 连形参都没有 —— 上游想显式强制也**无参数可传**。

后果：无 API Key 环境下，整条聊天链路在**构造期**抛 `ValueError`，
阶段 D 的 harness 因此被迫对 `create_llm` + `OpenAILLM` 做全覆盖 patch。

## 本文件钉住的口径（决策 1 丙 + 决策 2 归一）

```text
单一真源：环境变量（AI_SERVICE_MOCK_LLM 为主，USE_MOCK_LLM 过渡期兼容别名）
显式优先：显式传 use_mock=True/False 时以显式值为准
兜底跟随：use_mock=None（含不传的默认值）时读环境
装配透传：Center/Agent 层接受 use_mock_llm 形参并向下转发，保证可显式强制
```

| 编号 | 断言 |
|---|---|
| `MC-A01..A05` | 开关归一：仅 `USE_MOCK_LLM=1` 也生效；两个读取入口同源 |
| `MC-B01..B06` | `create_llm` / `OpenAILLM` 的 `None` 语义 + 显式优先 |
| `MC-C01..C02` | 无 Key 环境：开 mock 可离线构造 / 未开 mock 报统一可定位错误 |
| `MC-D01..D06` | 防退化锁：装配链每层都有旗标形参并向下转发 |

**Task 1 时本文件预期 RED**（A/B/D 组 + C01）；Task 2–3 逐步转绿。
`MC-B03/B04/C02` 是**显式优先**与**错误语义**的锚点，Task 1 起即应为 GREEN。
"""

import ast
import importlib
from pathlib import Path

import pytest

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
CENTERS_DIR = AI_SERVICE_DIR / "app" / "centers"
AGENTS_DIR = AI_SERVICE_DIR / "app" / "agents"
INTERNAL_API_INIT = AI_SERVICE_DIR / "internal_api" / "__init__.py"
CONVERSATION_COMPRESS = AI_SERVICE_DIR / "app" / "utils" / "conversation_compress.py"

# 构造真实 provider 所需凭据（清空它们 = 模拟"无 Key 环境"）。
# 注意：conftest.py 会 load_dotenv()，本地 .env 可能有真 Key，故必须显式清空。
_LLM_CREDENTIAL_ENVS = (
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
    "SPARK_APP_ID",
    "SPARK_API_KEY",
    "SPARK_API_SECRET",
)

# 决策 2：归一为 AI_SERVICE_MOCK_LLM，USE_MOCK_LLM 作过渡期兼容别名。
_PRIMARY_MOCK_ENV = "AI_SERVICE_MOCK_LLM"
_LEGACY_MOCK_ENV = "USE_MOCK_LLM"

# 决策 1：本轮接受 use_mock_llm 形参并向惰性默认构造转发的 Center。
# 含 plan_center / resource_center —— `ChatCenter._get_dispatcher()` 会构造它们，
# 所以它们也必须能接这个参数，否则运行时 TypeError（契约补全：5 → 7）。
_CENTERS_WITH_FLAG = [
    "chat_center",
    "auto_center",
    "plan_center",
    "resource_center",
    "exercise_center",
    "tutor_center",
    "visualization_center",
]

# 决策 1：本轮补齐 use_mock_llm 形参的 Agent（非 BaseAgent 直连旗标的两个）。
_AGENTS_WITH_FLAG = ["adjustment_agent", "diagnose_agent"]


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════


def _clear_mock_envs(monkeypatch) -> None:
    monkeypatch.delenv(_PRIMARY_MOCK_ENV, raising=False)
    monkeypatch.delenv(_LEGACY_MOCK_ENV, raising=False)


def _clear_llm_credentials(monkeypatch) -> None:
    for name in _LLM_CREDENTIAL_ENVS:
        monkeypatch.delenv(name, raising=False)


def _unified_flag_fn():
    """取统一 mock 开关函数；Task 2 之前不存在 → 返回 None。"""
    module = importlib.import_module("app.services.llm_service")
    return getattr(module, "_env_mock_flag", None)


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func_node(path: Path, name: str):
    for node in ast.walk(_module_ast(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _param_names(func) -> set[str]:
    args = func.args
    names = {a.arg for a in list(args.args) + list(args.kwonlyargs)}
    return names


# 会间接创建 LLM 的构造点后缀（Workflow / Pipeline 内部同样构造 Agent）
_CTOR_SUFFIXES = ("Agent", "Center", "Workflow", "Pipeline")


def _ctor_calls_missing_flag(func) -> list[str]:
    """「以 Agent/Center/Workflow/Pipeline 结尾、却没传 use_mock_llm」的构造调用名。"""
    offenders: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            name = target.attr
        else:
            continue
        if not name.endswith(_CTOR_SUFFIXES):
            continue
        if not any(kw.arg == "use_mock_llm" for kw in node.keywords):
            offenders.append(name)
    return offenders


# ═══════════════════════════════════════════════════════════════════
# Part A —— 开关归一（决策 2）
# ═══════════════════════════════════════════════════════════════════


class TestSwitchUnification:

    def test_mc_a01_legacy_env_alone_enables_unified_flag(self, monkeypatch):
        """仅设旧开关 `USE_MOCK_LLM=1`，统一开关也必须为真。

        过渡期兼容别名：老环境（只配了 USE_MOCK_LLM）行为只增不减。
        """
        _clear_mock_envs(monkeypatch)
        monkeypatch.setenv(_LEGACY_MOCK_ENV, "1")
        flag = _unified_flag_fn()
        assert flag is not None, "统一开关函数 app.services.llm_service._env_mock_flag 不存在"
        assert flag() is True

    def test_mc_a02_primary_env_alone_enables_unified_flag(self, monkeypatch):
        """仅设主开关 `AI_SERVICE_MOCK_LLM=1` → 统一开关为真。"""
        _clear_mock_envs(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        flag = _unified_flag_fn()
        assert flag is not None, "统一开关函数 app.services.llm_service._env_mock_flag 不存在"
        assert flag() is True

    def test_mc_a03_no_env_is_false(self, monkeypatch):
        """两个开关都未设 → False（生产默认）。"""
        _clear_mock_envs(monkeypatch)
        flag = _unified_flag_fn()
        assert flag is not None, "统一开关函数 app.services.llm_service._env_mock_flag 不存在"
        assert flag() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_mc_a04_truthy_values_accepted(self, monkeypatch, value):
        """真值字面量与既有 `_get_mock_flag()` 口径一致。"""
        _clear_mock_envs(monkeypatch)
        monkeypatch.setenv(_LEGACY_MOCK_ENV, value)
        flag = _unified_flag_fn()
        assert flag is not None, "统一开关函数 app.services.llm_service._env_mock_flag 不存在"
        assert flag() is True

    def test_mc_a05_internal_api_flag_shares_same_source(self, monkeypatch):
        """`internal_api._get_mock_flag()` 必须与统一开关**同源**（消除双源）。"""
        _clear_mock_envs(monkeypatch)
        monkeypatch.setenv(_LEGACY_MOCK_ENV, "1")
        internal_api = importlib.import_module("internal_api")
        assert internal_api._get_mock_flag() is True, (
            "internal_api._get_mock_flag 不认 USE_MOCK_LLM —— 两个读取入口仍是双源"
        )


# ═══════════════════════════════════════════════════════════════════
# Part B —— `use_mock=None` 语义 + 显式优先（决策 1 丙）
# ═══════════════════════════════════════════════════════════════════


class TestNoneSemantics:

    def test_mc_b01_create_llm_explicit_none_follows_env(self, monkeypatch):
        """`create_llm(use_mock=None)` + 环境开 mock → 不构造真实 provider。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        module = importlib.import_module("app.services.llm_service")
        llm = module.create_llm(use_mock=None)
        assert llm.use_mock is True

    def test_mc_b02_create_llm_default_follows_env(self, monkeypatch):
        """不传 `use_mock`（默认 None）+ 环境开 mock → 跟随环境。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        module = importlib.import_module("app.services.llm_service")
        llm = module.create_llm()
        assert llm.use_mock is True

    def test_mc_b03_create_llm_explicit_false_wins(self, monkeypatch):
        """显式 `use_mock=False` 优先于环境 —— 不能把生产改成 mock。"""
        _clear_mock_envs(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-explicit-false")
        module = importlib.import_module("app.services.llm_service")
        llm = module.create_llm(use_mock=False)
        assert llm.use_mock is False

    def test_mc_b04_create_llm_explicit_true_wins(self, monkeypatch):
        """显式 `use_mock=True` 在无 Key 环境也能构造成功。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        module = importlib.import_module("app.services.llm_service")
        llm = module.create_llm(use_mock=True)
        assert llm.use_mock is True

    def test_mc_b05_openai_llm_explicit_none_follows_env(self, monkeypatch):
        """`OpenAILLM(use_mock=None)` 是另一条构造路径，必须同样跟随环境。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        module = importlib.import_module("app.services.llm_service")
        llm = module.OpenAILLM(use_mock=None)
        assert llm.use_mock is True

    def test_mc_b06_openai_llm_default_follows_env(self, monkeypatch):
        """`OpenAILLM()` 不传 + 环境开 mock → 跟随环境。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")
        module = importlib.import_module("app.services.llm_service")
        llm = module.OpenAILLM()
        assert llm.use_mock is True


# ═══════════════════════════════════════════════════════════════════
# Part C —— 无 Key 环境的端到端构造
# ═══════════════════════════════════════════════════════════════════


class TestOfflineConstruction:

    def test_mc_c01_chat_center_constructible_without_keys(self, monkeypatch):
        """**本轮核心验收**：无 Key + 开 mock → 真实聊天链路入口不 patch 即可构造。

        走 `internal_api._get_chat_center()`（生产真实入口，装配层按统一开关显式传参），
        而非 `ChatCenter()` 裸构造 —— 环境读取**只集中在装配层与 llm_service 两处**，
        Center 裸构造保持"默认不读环境"的显式边界。

        这正是阶段 D harness 被迫做全覆盖 patch 的那条路径。
        """
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)
        monkeypatch.setenv(_PRIMARY_MOCK_ENV, "1")

        internal_api = importlib.import_module("internal_api")
        monkeypatch.setattr(internal_api, "_chat_center_singleton", None)

        center = internal_api._get_chat_center()
        assert center._get_dispatcher() is not None

    def test_mc_c02_no_key_without_mock_raises_clear_error(self, monkeypatch):
        """无 Key 且**未开** mock → 必须是统一、可定位的配置错误（锚点用例）。"""
        _clear_mock_envs(monkeypatch)
        _clear_llm_credentials(monkeypatch)

        from app.centers.chat_center import ChatCenter

        with pytest.raises(ValueError) as excinfo:
            ChatCenter()._get_dispatcher()
        assert "must be set" in str(excinfo.value), (
            f"错误信息不含配置指引，不利于定位：{excinfo.value}"
        )


# ═══════════════════════════════════════════════════════════════════
# Part D —— 防退化锁（AST）
# ═══════════════════════════════════════════════════════════════════


class TestAssemblyFlagLock:

    def test_mc_d01_chat_center_accepts_flag(self):
        """`ChatCenter.__init__` 必须接受 `use_mock_llm`（否则无法显式强制）。"""
        func = _func_node(CENTERS_DIR / "chat_center.py", "__init__")
        assert func is not None, "chat_center.py 找不到 __init__"
        assert "use_mock_llm" in _param_names(func), (
            "ChatCenter.__init__ 没有 use_mock_llm 形参 —— 调用方无法显式强制 mock"
        )

    def test_mc_d02_dispatcher_forwards_flag_to_every_agent_and_center(self):
        """`_get_dispatcher()` 里每个 Agent/Center 构造点都必须传 `use_mock_llm`。

        这是缺陷主因：8 Agent + 5 Center 全部无参构造 → 无 Key 环境构造期抛错。
        """
        func = _func_node(CENTERS_DIR / "chat_center.py", "_get_dispatcher")
        assert func is not None, "chat_center.py 找不到 _get_dispatcher"
        offenders = _ctor_calls_missing_flag(func)
        assert offenders == [], (
            "_get_dispatcher 里这些构造点没传 use_mock_llm（无 Key 环境会构造真实 provider）：\n"
            + "\n".join(sorted(set(offenders)))
        )

    def test_mc_d03_internal_api_chat_center_factory_passes_flag(self):
        """`internal_api._get_chat_center()` 必须传 `use_mock_llm=_get_mock_flag()`。"""
        func = _func_node(INTERNAL_API_INIT, "_get_chat_center")
        assert func is not None, "internal_api/__init__.py 找不到 _get_chat_center"
        passed = False
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "ChatCenter":
                if any(kw.arg == "use_mock_llm" for kw in node.keywords):
                    passed = True
        assert passed, "_get_chat_center() 裸调 ChatCenter() —— 聊天链路不认 mock 开关"

    @pytest.mark.parametrize("module_name", _CENTERS_WITH_FLAG)
    def test_mc_d04_centers_accept_flag(self, module_name):
        """5 个 Center 的 `__init__` 都要接受 `use_mock_llm`。"""
        func = _func_node(CENTERS_DIR / f"{module_name}.py", "__init__")
        assert func is not None, f"{module_name}.py 找不到 __init__"
        assert "use_mock_llm" in _param_names(func), (
            f"{module_name} 的 __init__ 没有 use_mock_llm 形参"
        )

    @pytest.mark.parametrize("module_name", _AGENTS_WITH_FLAG)
    def test_mc_d05_agents_accept_flag(self, module_name):
        """`AdjustmentAgent` / `DiagnoseAgent` 也要接受 `use_mock_llm`。"""
        func = _func_node(AGENTS_DIR / f"{module_name}.py", "__init__")
        assert func is not None, f"{module_name}.py 找不到 __init__"
        assert "use_mock_llm" in _param_names(func), (
            f"{module_name} 的 __init__ 没有 use_mock_llm 形参（非 BaseAgent 子类，需显式补）"
        )

    @pytest.mark.parametrize("func_name", ["llm_summarize", "self_compress"])
    def test_mc_d06_conversation_compress_accepts_mock(self, func_name):
        """会话摘要两个函数要能接收 mock 旗标（聊天链路的摘要分支）。"""
        func = _func_node(CONVERSATION_COMPRESS, func_name)
        assert func is not None, f"conversation_compress.py 找不到 {func_name}"
        assert "use_mock" in _param_names(func), (
            f"{func_name} 没有 use_mock 形参 —— 该分支的 create_llm 只能靠环境兜底"
        )

    def test_mc_d07_chat_task_dispatcher_forwards_flag(self):
        """`ChatTaskDispatcher.__init__` 的默认 Center 构造也要继承旗标。"""
        func = _func_node(CENTERS_DIR / "chat_task_dispatcher.py", "__init__")
        assert func is not None, "chat_task_dispatcher.py 找不到 __init__"
        assert "use_mock_llm" in _param_names(func), (
            "ChatTaskDispatcher.__init__ 没有 use_mock_llm 形参"
        )
        offenders = _ctor_calls_missing_flag(func)
        assert offenders == [], (
            "ChatTaskDispatcher.__init__ 里这些构造点没传 use_mock_llm：\n"
            + "\n".join(sorted(set(offenders)))
        )

    @pytest.mark.parametrize(
        "module_name,func_name",
        [
            ("auto_center", "_maybe_visualize"),
            ("plan_center", "_exercise_center"),
        ],
    )
    def test_mc_d08_lazy_center_ctors_forward_flag(self, module_name, func_name):
        """惰性构造 Center / Pipeline 的位置同样要继承旗标（**本轮实测发现的漏网点**）。

        不透传 `VisualizePipeline` 时它在无 Key 环境构造失败、被 `except` 静默吞掉，
        图解与 `analyze` 节点事件会一起消失（真链路 harness 帧数从 79 掉到 77）。
        """
        func = _func_node(CENTERS_DIR / f"{module_name}.py", func_name)
        assert func is not None, f"{module_name}.py 找不到 {func_name}"
        offenders = _ctor_calls_missing_flag(func)
        assert offenders == [], (
            f"{module_name}.{func_name} 里这些构造点没传 use_mock_llm：\n"
            + "\n".join(sorted(set(offenders)))
        )
