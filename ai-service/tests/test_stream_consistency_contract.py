"""流式阶段 C 的 C4/C5 契约：一致性验证 + 开关与扩展。

**C4（一致性）** —— 设计文档阶段 C 第 4 条「验证 token、节点、状态事件与最终结果的一致性」：
- `CS-A01` 逐对象对比：`ainvoke` 终态 == `ainvoke_with_events` 终态（逐字段）
- `CS-A02` 节点事件**覆盖图的全部节点**（不遗漏、不重复发）
- `CS-A03` 事件顺序 == 实际执行顺序
- `CS-A04` 图流开销可测（宽松上限，防病态退化；不作硬性能断言）

**C5（开关与扩展）**：
- `CS-B01` 图流**默认开启**：`BaseWorkflow.run` 会产出节点事件
- `CS-B02` `AI_SERVICE_GRAPH_STREAM=0` → 一键退回：无节点事件、结果一致
- `CS-B03` Workflow 节点里**嵌套调用的 Agent** 也把内层节点事件汇入同一条流
"""

import ast
import time
from pathlib import Path

import pytest
from langgraph.graph import END, StateGraph

from app.agents.base_agent import current_emitter
from app.events.graph_stream import ainvoke_with_events, graph_stream_enabled
from app.events.stream import ProgressEventType, StreamEmitter

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════
# 被测对象
# ═══════════════════════════════════════════════════════════════════


def _tiny_graph(prefix: str = "t"):
    """确定性的 3 节点小图（不触网不触库）。"""

    async def one(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), f"{prefix}1"]}

    async def two(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), f"{prefix}2"]}

    async def three(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), f"{prefix}3"]}

    graph = StateGraph(dict)
    graph.add_node("one", one)
    graph.add_node("two", two)
    graph.add_node("three", three)
    graph.set_entry_point("one")
    graph.add_edge("one", "two")
    graph.add_edge("two", "three")
    graph.add_edge("three", END)
    return graph.compile()


def _profile_agent_with_spies():
    """真实 ProfileAgent + 节点换成确定性 spy（避开 DB/网络，节点集合保持真实）。"""
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent(use_mock_llm=True)

    def _spy(name):
        async def _node(state):
            return {}
        return _node

    for name in ("extract", "merge", "respond"):
        setattr(agent, name, _spy(name))
    agent._semantic_judge_node = _spy("semantic_judge")
    agent._audit_node = _spy("audit")
    agent._compiled_graph = agent.build_graph()
    return agent


TARGETS = [
    pytest.param(
        lambda: _tiny_graph(), {"trace": []}, id="tiny_graph",
    ),
    pytest.param(
        lambda: _profile_agent_with_spies()._compiled_graph,
        {"messages": [{"role": "user", "content": "hi"}]},
        id="profile_agent_graph",
    ),
]


# ═══════════════════════════════════════════════════════════════════
# C4 —— 一致性
# ═══════════════════════════════════════════════════════════════════


class TestConsistency:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("factory,input_state", TARGETS)
    async def test_cs_a01_final_state_matches_ainvoke(self, factory, input_state):
        """逐对象验证：流式终态与 `ainvoke` 终态逐字段一致。"""
        graph = factory()

        invoked = await graph.ainvoke(dict(input_state))
        streamed = await ainvoke_with_events(
            graph, dict(input_state), emitter=StreamEmitter(),
        )

        assert streamed == invoked, f"终态不一致：{streamed} != {invoked}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("factory,input_state", TARGETS)
    async def test_cs_a02_node_events_cover_every_node(self, factory, input_state):
        """节点事件必须覆盖图的**全部**节点，且每个节点只发一次。"""
        graph = factory()
        declared = set(graph.get_graph().nodes)
        emitter = StreamEmitter()

        await ainvoke_with_events(graph, dict(input_state), emitter=emitter)

        reported = [
            event.data["node"] for event in emitter.events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        # 图的 `get_graph().nodes` 含 `__start__` / `__end__` 伪节点，从期望集里去掉
        expected = declared - {"__start__", "__end__"}

        assert set(reported) == expected, f"节点覆盖不全：报出 {set(reported)}，应覆盖 {expected}"
        assert len(reported) == len(expected), f"节点事件有重复：{reported}"
        assert all(event.data["depth"] == 0 for event in emitter.events
                   if event.type is ProgressEventType.NODE_COMPLETED)

    @pytest.mark.asyncio
    async def test_cs_a03_event_order_matches_declared_execution_order(self):
        emitter = StreamEmitter()
        await ainvoke_with_events(_tiny_graph(), {"trace": []}, emitter=emitter)

        assert [
            event.data["node"] for event in emitter.events
            if event.type is ProgressEventType.NODE_COMPLETED
        ] == ["one", "two", "three"]

    @pytest.mark.asyncio
    async def test_cs_a04_streaming_overhead_is_bounded(self):
        """图流开销宽松上限（防病态退化）；不做硬性能断言，只记录实测值。"""
        graph = _tiny_graph()

        start = time.perf_counter()
        for _ in range(5):
            await graph.ainvoke({"trace": []})
        plain = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(5):
            await ainvoke_with_events(graph, {"trace": []}, emitter=StreamEmitter())
        streamed = time.perf_counter() - start

        print(f"\n[CS-A04] ainvoke x5 = {plain*1000:.1f}ms, astream x5 = {streamed*1000:.1f}ms")
        assert streamed < plain * 20 + 2.0, (
            f"图流开销异常：plain={plain:.4f}s streamed={streamed:.4f}s"
        )


# ═══════════════════════════════════════════════════════════════════
# C5 —— 开关与扩展
# ═══════════════════════════════════════════════════════════════════


class _RecordingWorkflow:
    """最小 Workflow：记录本次执行拿到的事件（用于验证基类接线）。"""

    pass


def _make_minimal_workflow(nested_agent=None):
    """构造一个真实 `BaseWorkflow` 子类：workflow 节点 [可选嵌套 Agent] → done。"""
    from app.workflows.base_workflow import BaseWorkflow

    class _State(dict):
        pass

    class MinimalWorkflow(BaseWorkflow):
        def _build_graph(self):
            async def first(state: dict) -> dict:
                return {"trace": [*(state.get("trace") or []), "wf_first"]}

            async def second(state: dict) -> dict:
                if nested_agent is not None:
                    inner = await nested_agent.run({"messages": [{"role": "user", "content": "hi"}]})
                    return {"trace": [*(state.get("trace") or []), "wf_second"], "inner": bool(inner)}
                return {"trace": [*(state.get("trace") or []), "wf_second"]}

            graph = StateGraph(dict)
            graph.add_node("first", first)
            graph.add_node("second", second)
            graph.set_entry_point("first")
            graph.add_edge("first", "second")
            graph.add_edge("second", END)
            return graph.compile()

    return MinimalWorkflow(use_mock=True)


class TestSwitchAndExtension:

    def test_cs_b00_flag_defaults_to_on(self, monkeypatch):
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)
        assert graph_stream_enabled() is True

        for value in ("0", "false", "no", "off"):
            monkeypatch.setenv("AI_SERVICE_GRAPH_STREAM", value)
            assert graph_stream_enabled() is False

    @pytest.mark.asyncio
    async def test_cs_b01_workflow_emits_node_events_by_default(
        self, monkeypatch, caplog,
    ):
        """默认开启：真实 `BaseWorkflow.run` 产出节点事件（并打一行节点轨迹日志）。"""
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)

        captured: list[StreamEmitter] = []
        real_init = StreamEmitter.__init__

        def _spy_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            captured.append(self)

        monkeypatch.setattr(StreamEmitter, "__init__", _spy_init)

        workflow = _make_minimal_workflow()
        with caplog.at_level("INFO"):
            result = await workflow.run({"trace": []})

        assert result["trace"] == ["wf_first", "wf_second"]
        assert captured, "BaseWorkflow 未创建事件源"
        nodes = [
            event.data["node"] for event in captured[0].events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        assert nodes == ["first", "second"], f"workflow 节点事件异常：{nodes}"
        assert "node event(s)" in caplog.text, "缺少节点轨迹日志"

    @pytest.mark.asyncio
    async def test_cs_b02_flag_off_falls_back_to_ainvoke(self, monkeypatch):
        """`AI_SERVICE_GRAPH_STREAM=0` → 无事件、结果一致（一键回退）。"""
        monkeypatch.setenv("AI_SERVICE_GRAPH_STREAM", "0")

        captured: list[StreamEmitter] = []
        real_init = StreamEmitter.__init__

        def _spy_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            captured.append(self)

        monkeypatch.setattr(StreamEmitter, "__init__", _spy_init)

        workflow = _make_minimal_workflow()
        result = await workflow.run({"trace": []})

        assert result["trace"] == ["wf_first", "wf_second"], "回退路径结果必须一致"
        assert captured == [], "关闭后不应创建事件源"

    @pytest.mark.asyncio
    async def test_cs_b03_nested_agent_nodes_join_the_same_stream(
        self, monkeypatch,
    ):
        """Workflow 节点里嵌套调用的 Agent，其内层节点事件汇入**同一条**流。

        这是 C5「扩展」的核心：不用给每个 Agent 单独接线 —— 只要 Workflow 层注入了
        事件源（`current_emitter`），嵌套的 `agent.run()` 会自动继承。
        """
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)

        captured: list[StreamEmitter] = []
        real_init = StreamEmitter.__init__

        def _spy_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            captured.append(self)

        monkeypatch.setattr(StreamEmitter, "__init__", _spy_init)

        agent = _profile_agent_with_spies()
        workflow = _make_minimal_workflow(nested_agent=agent)
        await workflow.run({"trace": []})

        assert captured, "未创建事件源"
        nodes = [
            event.data["node"] for event in captured[0].events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        assert {"first", "second"} <= set(nodes), nodes
        # 内层 Agent 的节点应带 namespace（层级深度 > 0）
        nested = [
            event.data["node"] for event in captured[0].events
            if event.type is ProgressEventType.NODE_COMPLETED and event.data["depth"] > 0
        ]
        assert {"extract", "semantic_judge", "merge", "audit", "response"} <= set(nested), (
            f"嵌套 Agent 的内层节点事件未汇入同一条流：{nested}"
        )
