"""GUIDE P3-B3a：状态范围 / 节点复用协议 / 分发职责 的契约锁定。

回答《三类决策与命名约定》§5「状态范围约定」的三条：
  - 逐请求状态不得挂在 Agent 实例上（本轮修 `_current_on_token`）
  - Workflow 复用 Agent 的局部节点，必须走**公开节点 API**（不得跨类调 `_private`）
  - Center 的 mode→Center 分发必须显式（不靠 if-链堆叠）

四部分：

- **Part A（`ST-A01..A04`）**：逐请求回调隔离（`contextvars`）。
  `ST-A03` 是**行为级并发用例**：同一实例两个并发 `run()`，节点在 `await` 之后再读回调，
  必须仍是**本协程**的回调 —— 旧实现（实例属性）会被另一个请求覆盖。
- **Part B（`ST-B01..B02`）**：节点复用协议。
- **Part C（`ST-C01..C02`）**：`_execute_task` 表驱动 + 未知 mode / 异常语义不变。
- **Part D（`ST-D01..D02`）**：`ResultAgent` → `ChatTaskDispatcher` 的命名与唯一引用者。

⚠️ 本文件在 Task 1 时为红（尚未实施），实施后转绿。
"""

import ast
import asyncio
from pathlib import Path

import pytest

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = AI_SERVICE_DIR / "app"


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════


def _source(relative: str) -> str:
    return (AI_SERVICE_DIR / relative).read_text(encoding="utf-8")


def _iter_app_py() -> list[Path]:
    return sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _referencing_files(target_module: str) -> set[str]:
    """`app/**` 内 import 了 `target_module` 的文件（posix 相对路径）。"""
    hits: set[str] = set()
    for path in _iter_app_py():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == target_module or node.module.startswith(target_module + ".")
            ):
                hits.add(path.relative_to(AI_SERVICE_DIR).as_posix())
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == target_module or alias.name.startswith(target_module + "."):
                        hits.add(path.relative_to(AI_SERVICE_DIR).as_posix())
    return hits


def _on_token_var():
    """生产代码暴露的「逐请求回调」ContextVar（P3-B3a 引入）。"""
    from app.agents.base_agent import current_on_token  # noqa: WPS433 (RED 时故意失败)

    return current_on_token


# ═══════════════════════════════════════════════════════════════════
# Part A —— 逐请求回调隔离
# ═══════════════════════════════════════════════════════════════════


class TestPerRequestCallbackIsolation:

    def test_st_a01_base_agent_never_stores_callback_on_instance(self):
        """`BaseAgent` 不得把回调写进实例属性（`self._current_on_token`）。"""
        tree = ast.parse(_source("app/agents/base_agent.py"))
        offenders = [
            f"{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "_current_on_token"
        ]
        assert offenders == [], (
            f"base_agent 仍在实例上读写 _current_on_token（行号 {offenders}）"
        )

    def test_st_a02_tutor_agent_reads_callback_from_context_not_instance(self):
        """`TutorAgent` 不得从实例读回调。"""
        source = _source("app/agents/tutor_agent.py")
        assert '_current_on_token' not in source, (
            "tutor_agent 仍从实例属性读回调"
        )

    def test_st_a03_exposes_module_level_context_var(self):
        """回调必须是模块级 `ContextVar`（每协程隔离）。"""
        var = _on_token_var()
        assert var.get() is None, "ContextVar 默认值应为 None"

    @pytest.mark.asyncio
    async def test_st_a04_concurrent_runs_on_same_instance_do_not_crosstalk(self):
        """同一实例并发两次 `run()`：各自只收到自己的 token。

        探针节点**在 `await` 之后重新读取**回调 —— 这是 `contextvars` 的保证，
        实例属性实现会被另一个并发请求覆盖（故本用例在旧实现下为红）。
        """
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict

        from app.agents.base_agent import BaseAgent

        class _ProbeState(TypedDict, total=False):
            tag: str

        var = _on_token_var()

        class _ProbeAgent(BaseAgent):
            def __init__(self):
                super().__init__("probe", use_mock_llm=True)

            def _load_prompt(self, filename="system.yaml", variables=None, key="system"):
                return ""  # 探针不需要 prompt 文件

            def build_graph(self):
                graph = StateGraph(_ProbeState)
                graph.add_node("emit", self._emit_node)
                graph.set_entry_point("emit")
                graph.add_edge("emit", END)
                return graph.compile()

            async def _emit_node(self, state):
                await asyncio.sleep(0.02)
                on_token = var.get()  # ← await 之后重新读取
                if on_token is not None:
                    await on_token(state["tag"])
                return {}

        agent = _ProbeAgent()

        async def one_run(tag: str, sink: list[str]):
            async def on_token(chunk: str) -> None:
                sink.append(chunk)

            await agent.run({"tag": tag, "_on_token": on_token})

        sink_a: list[str] = []
        sink_b: list[str] = []
        await asyncio.gather(one_run("A", sink_a), one_run("B", sink_b))

        assert sink_a == ["A"], f"请求 A 收到了不属于它的 token：{sink_a}"
        assert sink_b == ["B"], f"请求 B 收到了不属于它的 token：{sink_b}"

    @pytest.mark.asyncio
    async def test_st_a05_callback_is_consumed_and_not_leaked(self):
        """单请求路径：回调可用；运行结束后不残留在实例上。"""
        from langgraph.graph import END, StateGraph
        from typing_extensions import TypedDict

        from app.agents.base_agent import BaseAgent

        class _ProbeState(TypedDict, total=False):
            tag: str

        var = _on_token_var()

        class _ProbeAgent(BaseAgent):
            def __init__(self):
                super().__init__("probe", use_mock_llm=True)

            def _load_prompt(self, filename="system.yaml", variables=None, key="system"):
                return ""

            def build_graph(self):
                graph = StateGraph(_ProbeState)
                graph.add_node("emit", self._emit_node)
                graph.set_entry_point("emit")
                graph.add_edge("emit", END)
                return graph.compile()

            async def _emit_node(self, state):
                on_token = var.get()
                if on_token is not None:
                    await on_token(state["tag"])
                return {}

        agent = _ProbeAgent()
        seen: list[str] = []

        async def on_token(chunk: str) -> None:
            seen.append(chunk)

        await agent.run({"tag": "X", "_on_token": on_token})

        assert seen == ["X"]
        assert var.get() is None, "回调未随请求结束而复位（上下文泄漏）"


# ═══════════════════════════════════════════════════════════════════
# Part B —— 节点复用协议
# ═══════════════════════════════════════════════════════════════════


class TestNodeReuseProtocol:

    @pytest.mark.parametrize(
        "relative,names",
        [
            ("app/agents/profile_agent.py", ["extract", "merge", "respond"]),
            ("app/agents/path_agent.py", ["draft", "revise"]),
        ],
    )
    def test_st_b01_agents_expose_public_node_api(self, relative, names):
        """被 Workflow 复用的节点必须有**公开**入口。"""
        tree = ast.parse(_source(relative))
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or isinstance(node, ast.ClassDef)
        }
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            defined.update(m.name for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
        missing = [n for n in names if n not in defined]
        assert missing == [], f"{relative} 缺少公开节点 API：{missing}（现有：{sorted(defined)}）"

    @pytest.mark.parametrize(
        "relative",
        [
            "app/workflows/profile_workflow.py",
            "app/workflows/learning_path.py",
        ],
    )
    def test_st_b02_workflows_do_not_call_private_node_methods(self, relative):
        """Workflow 不得跨类调用 `_xxx_node` 私有节点。"""
        source = _source(relative)
        offenders = [
            name
            for name in (
                "._extract_node(",
                "._merge_node(",
                "._response_node(",
                "._draft_node(",
                "._revise_node(",
                "._completeness_check_node(",
            )
            if name in source
        ]
        assert offenders == [], f"{relative} 仍穿透私有节点：{offenders}"


# ═══════════════════════════════════════════════════════════════════
# Part C —— mode→Center 分发
# ═══════════════════════════════════════════════════════════════════

DISPATCHER_MODULE = "app/centers/chat_task_dispatcher.py"


def _dispatcher_source() -> str:
    """分发器源码。P3-B3a 起固定在 `chat_task_dispatcher.py`（旧模块已由 ST-D01 断言不存在）。"""
    path = AI_SERVICE_DIR / DISPATCHER_MODULE
    assert path.exists(), f"{DISPATCHER_MODULE} 不存在"
    return path.read_text(encoding="utf-8")


class TestCenterDispatch:

    def test_st_c01_execute_task_has_no_mode_if_chain(self):
        """`_execute_task` 不得再用 `if task.mode == "..."` 链。"""
        tree = ast.parse(_dispatcher_source())
        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute) \
                    and test.left.attr == "mode" \
                    and any(isinstance(c, ast.Constant) for c in test.comparators):
                offenders.append(node.lineno)
        assert offenders == [], f"仍存在 mode if-链（行号 {offenders}）"

    @pytest.mark.asyncio
    async def test_st_c02_unknown_mode_and_exception_semantics_unchanged(self):
        """未知 mode 与 Center 异常都给人话，技术原因留在 error_code，不把异常原文给用户。"""
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher
        from app.centers.schemas import CenterTask

        dispatcher = ChatTaskDispatcher()

        task = CenterTask(mode="__nope__", intent="unknown", input="x", sequence=0)

        class _BoomCenter:
            async def execute(self, task):  # noqa: ANN001
                raise RuntimeError("boom")

        dispatcher.plan_center = _BoomCenter()
        boom_task = CenterTask(mode="plan", intent="learning_path", input="x", sequence=1)

        unknown = await dispatcher._execute_task(task)
        assert unknown.error_code == "UNKNOWN_CENTER"
        assert "center" not in (unknown.error or "")

        failed = await dispatcher._execute_task(boom_task)
        assert failed.error_code == "TASK_FAILED"
        assert "boom" not in (failed.error or "")


# ═══════════════════════════════════════════════════════════════════
# Part D —— 命名与唯一引用者
# ═══════════════════════════════════════════════════════════════════


class TestDispatcherOwnership:

    def test_st_d01_module_renamed(self):
        old = AI_SERVICE_DIR / "app/centers/result_agent.py"
        new = AI_SERVICE_DIR / DISPATCHER_MODULE
        assert not old.exists(), "旧模块 result_agent.py 仍存在"
        assert new.exists(), f"{DISPATCHER_MODULE} 不存在"
        assert "class ChatTaskDispatcher" in new.read_text(encoding="utf-8")

    def test_st_d02_only_chat_center_references_dispatcher(self):
        """它只服务聊天域：生产代码里唯一引用者应是 `chat_center.py`。"""
        actual = _referencing_files("app.centers.chat_task_dispatcher")
        assert actual == {"app/centers/chat_center.py"}, (
            f"ChatTaskDispatcher 的引用者与约定不符：{sorted(actual)}"
        )
