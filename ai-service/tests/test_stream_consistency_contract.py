"""流式阶段 C 的 C4/C5 契约：一致性验证 + 开关与扩展。

**C4（一致性）** —— 设计文档阶段 C 第 4 条「验证 token、节点、状态事件与最终结果的一致性」：
- `CS-A01` 逐对象对比：`ainvoke` 终态 == `ainvoke_with_events` 终态（逐字段）
- `CS-A02` 节点事件**覆盖图的全部节点**（不遗漏、不重复发）
- `CS-A03` 事件顺序 == 实际执行顺序
- `CS-A04` 图流开销可测（宽松上限，防病态退化；不作硬性能断言）
- `CS-A05` **真实 Workflow**（生产 `_build_graph` + 内层嵌套 Agent）终态与 `ainvoke` 逐字段一致
- `CS-A06` 真实 Workflow 的节点事件覆盖外层（depth=0）与内层（depth>0）
- `CS-A07` 大 state 下 `values` 快照开销的实测与上限（默认开启的代价被量化）

**C5（开关与扩展）**：
- `CS-B01` 图流**默认开启**：`BaseWorkflow.run` 会产出节点事件
- `CS-B02` `AI_SERVICE_GRAPH_STREAM=0` → 一键退回：无节点事件、结果一致
- `CS-B03` Workflow 节点里**嵌套调用的 Agent** 也把内层节点事件汇入同一条流
- `CS-B04` 上游已注入事件源时，Workflow **复用它**（同一 run_id，P0 修复回归）
- `CS-B05` 复用的上游事件源一路贯穿到嵌套 Agent 的内层节点
- `CS-B06` `AI_SERVICE_GRAPH_STREAM=0` 是**硬总闸**：即使上游注入了事件源也一律退回
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


def _profile_workflow_with_spies():
    """**真实** `ProfileWorkflow`（生产 `_build_graph`）+ 内层 Agent 换 spy。

    外层 3 节点（`pipeline` / `completeness_check` / `complete`）来自生产代码，
    其中 `pipeline` 节点手工嵌套 `ProfileAgent.run()`（5 节点 spy）—— 覆盖
    「真实 Workflow 图 + 手工嵌套 Agent」这一此前未被对账的形态（P1 修复）。
    """
    from app.workflows.profile_workflow import ProfileWorkflow

    workflow = ProfileWorkflow(use_mock=True)
    workflow.profile_agent = _profile_agent_with_spies()
    return workflow


def _bulky_graph(payload_chars: int = 200_000):
    """3 节点图，首节点写入大 payload —— 模拟「长文生成」路径的 state 体积。"""
    payload = "x" * payload_chars

    async def one(state: dict) -> dict:
        return {"blob": payload, "trace": [*(state.get("trace") or []), "b1"]}

    async def two(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "b2"]}

    async def three(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "b3"]}

    graph = StateGraph(dict)
    graph.add_node("one", one)
    graph.add_node("two", two)
    graph.add_node("three", three)
    graph.set_entry_point("one")
    graph.add_edge("one", "two")
    graph.add_edge("two", "three")
    graph.add_edge("three", END)
    return graph.compile()


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

    @pytest.mark.asyncio
    async def test_cs_a05_real_workflow_final_state_matches_ainvoke(self):
        """**真实 Workflow** 终态与 `ainvoke` 逐字段一致（P1 修复）。

        此前 TARGETS 只覆盖玩具图 + spy agent；本用例用生产 `_build_graph`
        构建的 `ProfileWorkflow`（`pipeline` 节点手工嵌套 Agent）做对账。
        """
        workflow = _profile_workflow_with_spies()
        input_state = {
            "messages": [{"role": "user", "content": "hi"}],
            "current_profile": {},
        }

        invoked = await workflow.graph.ainvoke(dict(input_state))
        streamed = await ainvoke_with_events(
            workflow.graph, dict(input_state), emitter=StreamEmitter(),
        )

        assert streamed == invoked, f"真实 Workflow 终态不一致：{streamed} != {invoked}"

    @pytest.mark.asyncio
    async def test_cs_a06_real_workflow_events_cover_top_and_nested(self):
        """真实 Workflow：外层节点（depth=0）与嵌套 Agent 内层节点（depth>0）都被覆盖。"""
        workflow = _profile_workflow_with_spies()
        emitter = StreamEmitter()

        await ainvoke_with_events(
            workflow.graph,
            {"messages": [{"role": "user", "content": "hi"}], "current_profile": {}},
            emitter=emitter,
        )

        node_events = [
            event for event in emitter.events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        top = {e.data["node"] for e in node_events if e.data["depth"] == 0}
        nested = {e.data["node"] for e in node_events if e.data["depth"] > 0}

        # 外层：pipeline → completeness_check →（画像不完整）END；`complete` 不执行
        assert {"pipeline", "completeness_check"} <= top, top
        assert {"extract", "semantic_judge", "merge", "audit", "response"} <= nested, nested

    @pytest.mark.asyncio
    async def test_cs_a07_bulky_state_overhead_is_measured_and_bounded(self):
        """大 state（模拟长文生成）下 `values` 全量快照开销：实测 + 有意义的上限。

        默认开启图流后，终态取自 `values` 模式 —— **每步全量快照**。本用例把
        这一代价量化（`pytest -s` 可见实测倍率），并设宽松但有意义的上限防静默退化。
        """
        graph = _bulky_graph(200_000)

        start = time.perf_counter()
        for _ in range(3):
            await graph.ainvoke({"blob": "", "trace": []})
        plain = time.perf_counter() - start

        start = time.perf_counter()
        for _ in range(3):
            await ainvoke_with_events(
                graph, {"blob": "", "trace": []}, emitter=StreamEmitter(),
            )
        streamed = time.perf_counter() - start

        ratio = streamed / plain if plain > 0 else float("inf")
        print(
            f"\n[CS-A07] bulky(200KB) x3: ainvoke={plain*1000:.1f}ms "
            f"astream={streamed*1000:.1f}ms ratio={ratio:.2f}x"
        )
        assert streamed < plain * 20 + 1.0, (
            f"大 state 下图流开销异常：ratio={ratio:.2f}x "
            f"(plain={plain:.4f}s streamed={streamed:.4f}s)"
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

    # ── P0 修复回归：emitter 复用（有上游就必须汇入上游）─────────────

    @pytest.mark.asyncio
    async def test_cs_b04_workflow_reuses_upstream_emitter(self, monkeypatch):
        """上游已注入事件源 → Workflow **复用**它（同一 run_id），不得自建。

        P0 回归：早前版本无条件 `StreamEmitter()` 覆盖上游，节点事件落入
        无消费者的局部实例，run_id 也与同请求不一致。
        """
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)

        upstream = StreamEmitter(run_id="upstream-run")
        token = current_emitter.set(upstream)
        try:
            workflow = _make_minimal_workflow()
            result = await workflow.run({"trace": []})
        finally:
            current_emitter.reset(token)

        assert result["trace"] == ["wf_first", "wf_second"]
        node_events = [
            event for event in upstream.events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        assert [e.data.get("node") for e in node_events] == ["first", "second"], (
            f"节点事件未汇入上游事件源：{[e.data for e in upstream.events]}"
        )
        assert all(e.run_id == "upstream-run" for e in upstream.events), (
            "事件 run_id 必须与上游一致（同一请求同一条流）"
        )

    @pytest.mark.asyncio
    async def test_cs_b05_upstream_emitter_reaches_nested_agent_nodes(self, monkeypatch):
        """复用的上游事件源一路贯穿到嵌套 Agent 的内层节点（带 namespace）。"""
        monkeypatch.delenv("AI_SERVICE_GRAPH_STREAM", raising=False)

        upstream = StreamEmitter(run_id="upstream-run")
        agent = _profile_agent_with_spies()
        token = current_emitter.set(upstream)
        try:
            workflow = _make_minimal_workflow(nested_agent=agent)
            await workflow.run({"trace": []})
        finally:
            current_emitter.reset(token)

        node_events = [
            event for event in upstream.events
            if event.type is ProgressEventType.NODE_COMPLETED
        ]
        top = {e.data["node"] for e in node_events if e.data["depth"] == 0}
        nested = {e.data["node"] for e in node_events if e.data["depth"] > 0}
        assert {"first", "second"} <= top, top
        assert {"extract", "semantic_judge", "merge", "audit", "response"} <= nested, nested
        assert all(e.run_id == "upstream-run" for e in upstream.events)

    @pytest.mark.asyncio
    async def test_cs_b06_flag_off_is_hard_master_switch(self, monkeypatch):
        """`AI_SERVICE_GRAPH_STREAM=0` 是硬总闸：即使上游注入了事件源也一律退回。

        锁住「一键退回」承诺：总闸关闭时不产生任何图流事件（上游事件源必须保持空）。
        """
        monkeypatch.setenv("AI_SERVICE_GRAPH_STREAM", "0")

        upstream = StreamEmitter(run_id="upstream-run")
        token = current_emitter.set(upstream)
        try:
            workflow = _make_minimal_workflow()
            result = await workflow.run({"trace": []})
        finally:
            current_emitter.reset(token)

        assert result["trace"] == ["wf_first", "wf_second"], "回退路径结果必须一致"
        assert upstream.events == [], "总闸关闭后上游事件源不应收到本工作流的事件"
