"""流式阶段 C 转换层契约（`app/events/graph_stream.py`）。

本层是「`ainvoke` 的等价替换」：**返回值必须一致**，额外只发节点事件。

| 编号 | 断言 |
|---|---|
| `GS-A01` | 节点事件覆盖每个节点，含**内层嵌套**节点，并带 `namespace` 层级路径 |
| `GS-A02` | **等价性**：返回值与 `ainvoke` 逐字段一致（回退路径成立的前提） |
| `GS-A03` | 不传 `emitter` → 直接走 `ainvoke`，返回值同样一致（零额外开销） |
| `GS-A04` | 订阅者抛异常不影响返回值与事件数量（横切逻辑不得拖垮主流程） |
| `GS-A05` | 事件顺序 = 实际执行顺序（外层节点与其内层节点的先后关系正确） |
| `GS-A06` | 本层不依赖 web 框架（与 `app/events/stream.py` 同一约束） |
"""

import ast
from pathlib import Path

import pytest
from langgraph.graph import END, StateGraph

from app.events.graph_stream import ainvoke_with_events
from app.events.stream import MessageDeltaCollector, ProgressEventType, StreamEmitter

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
MODULE_PATH = AI_SERVICE_DIR / "app/events/graph_stream.py"


def _build_inner_graph():
    """内层：inner_a → inner_b（模拟 ProfileAgent 这类被嵌套的图）。"""

    class _InnerState(dict):
        pass

    async def inner_a(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "inner_a"]}

    async def inner_b(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "inner_b"]}

    graph = StateGraph(dict)
    graph.add_node("inner_a", inner_a)
    graph.add_node("inner_b", inner_b)
    graph.set_entry_point("inner_a")
    graph.add_edge("inner_a", "inner_b")
    graph.add_edge("inner_b", END)
    return graph.compile()


def _build_outer_graph():
    """外层：outer_first → wrapped（内含 inner 图的手工 ainvoke）→ outer_last。"""
    inner = _build_inner_graph()

    async def outer_first(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "outer_first"]}

    async def wrapped(state: dict) -> dict:
        # 本项目现状：节点里直接 await 内层图的 ainvoke（不传 config）
        inner_result = await inner.ainvoke({"trace": state.get("trace") or []})
        return {
            "trace": inner_result["trace"],
            "inner_steps": len(inner_result["trace"]),
        }

    async def outer_last(state: dict) -> dict:
        return {"trace": [*(state.get("trace") or []), "outer_last"]}

    graph = StateGraph(dict)
    graph.add_node("outer_first", outer_first)
    graph.add_node("wrapped", wrapped)
    graph.add_node("outer_last", outer_last)
    graph.set_entry_point("outer_first")
    graph.add_edge("outer_first", "wrapped")
    graph.add_edge("wrapped", "outer_last")
    graph.add_edge("outer_last", END)
    return graph.compile()


@pytest.mark.asyncio
async def _run_with_emitter():
    graph = _build_outer_graph()
    emitter = StreamEmitter(run_id="gs-run")
    state = await ainvoke_with_events(graph, {"trace": []}, emitter=emitter)
    return graph, emitter, state


class TestGraphStreamAdapter:

    @pytest.mark.asyncio
    async def test_gs_a01_node_events_cover_nested_nodes_with_namespace(self):
        _graph, emitter, _state = await _run_with_emitter()

        node_events = [e for e in emitter.events if e.type is ProgressEventType.NODE_COMPLETED]
        top = {e.data["node"] for e in node_events if e.data["depth"] == 0}
        nested = {e.data["node"] for e in node_events if e.data["depth"] > 0}

        assert {"outer_first", "wrapped", "outer_last"} <= top, top
        assert {"inner_a", "inner_b"} <= nested, (
            f"内层节点事件缺失（这是阶段 C 的关键前提）：{nested}"
        )
        # 内层事件应带非空命名空间路径
        inner_event = next(e for e in node_events if e.data["node"] == "inner_a")
        assert inner_event.data["namespace"], "内层事件必须带 namespace"

    @pytest.mark.asyncio
    async def test_gs_a02_return_value_equals_ainvoke(self):
        graph = _build_outer_graph()

        invoked = await graph.ainvoke({"trace": []})
        _g, _emitter, streamed = await _run_with_emitter()

        assert streamed == invoked, "转换层返回值必须与 ainvoke 逐字段一致"

    @pytest.mark.asyncio
    async def test_gs_a03_without_emitter_matches_invoke(self):
        graph = _build_outer_graph()

        invoked = await graph.ainvoke({"trace": []})
        without = await ainvoke_with_events(graph, {"trace": []}, emitter=None)

        assert without == invoked

    @pytest.mark.asyncio
    async def test_gs_a04_broken_subscriber_does_not_affect_result(self):
        graph = _build_outer_graph()
        emitter = StreamEmitter()
        collector = MessageDeltaCollector()
        emitter.subscribe(lambda _e: (_ for _ in ()).throw(RuntimeError("subscriber boom")))
        emitter.subscribe(collector)

        invoked = await graph.ainvoke({"trace": []})
        result = await ainvoke_with_events(graph, {"trace": []}, emitter=emitter)

        assert result == invoked, "订阅者异常不得影响返回值"

    @pytest.mark.asyncio
    async def test_gs_a05_event_order_follows_execution_order(self):
        _graph, emitter, _state = await _run_with_emitter()

        order = [
            e.data["node"] for e in emitter.events
            if e.type is ProgressEventType.NODE_COMPLETED
        ]
        assert order == [
            "outer_first", "inner_a", "inner_b", "wrapped", "outer_last",
        ], f"事件顺序应与执行顺序一致：{order}"

    def test_gs_a06_no_web_dependency(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)

        banned = {m for m in modules if m.split(".")[0] in {"fastapi", "starlette", "uvicorn"}}
        assert banned == set(), f"转换层引入了 web 框架：{banned}"


# ═══════════════════════════════════════════════════════════════════
# Part C —— C3 试点接入：Agent 层（`BaseAgent.run` + `current_emitter`）
# ═══════════════════════════════════════════════════════════════════


def _spied_profile_agent(order: list[str]):
    """把 ProfileAgent 的 5 个节点换成不触网不触库的 spy，再重编图以捕获 spy。"""
    from app.agents.profile_agent import ProfileAgent

    agent = ProfileAgent(use_mock_llm=True)

    def _spy(name):
        async def _node(state):
            order.append(name)
            return {}
        return _node

    for name in ("extract", "merge", "respond"):
        setattr(agent, name, _spy(name))
    agent._semantic_judge_node = _spy("semantic_judge")
    agent._audit_node = _spy("audit")
    agent._compiled_graph = agent.build_graph()
    return agent


class TestAgentLevelWiring:

    @pytest.mark.asyncio
    async def test_gs_b01_agent_nodes_flow_into_injected_emitter(self):
        """注入 `current_emitter` 后，Agent **图节点**事件汇入同一条事件流。"""
        from app.agents.base_agent import current_emitter

        order: list[str] = []
        agent = _spied_profile_agent(order)
        emitter = StreamEmitter(run_id="agent-run")

        token = current_emitter.set(emitter)
        try:
            result = await agent.run({"messages": [{"role": "user", "content": "hi"}]})
        finally:
            current_emitter.reset(token)

        assert order == ["extract", "semantic_judge", "merge", "audit", "respond"], order
        node_events = [
            e.data["node"] for e in emitter.events
            if e.type is ProgressEventType.NODE_COMPLETED
        ]
        # 注意：事件里带的是**图节点名**（`build_graph` 里注册的名字），
        # 不是方法名 —— 最后一个节点注册为 "response"，其方法叫 `respond`。
        assert node_events == [
            "extract", "semantic_judge", "merge", "audit", "response",
        ], f"Agent 节点事件未汇入事件源：{node_events}"
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_gs_b02_without_emitter_no_node_events_and_same_result(self):
        """不注入事件源 → 走 `ainvoke` 旧路径：无节点事件，结果一致（默认零变化）。"""
        order_a: list[str] = []
        plain_agent = _spied_profile_agent(order_a)
        state = {"messages": [{"role": "user", "content": "hi"}]}
        plain_result = await plain_agent.run(dict(state))

        from app.agents.base_agent import current_emitter

        order_b: list[str] = []
        emitting_agent = _spied_profile_agent(order_b)
        emitter = StreamEmitter()
        token = current_emitter.set(emitter)
        try:
            emitting_result = await emitting_agent.run(dict(state))
        finally:
            current_emitter.reset(token)

        assert order_a == order_b, "注入事件源不得改变节点执行顺序"
        assert plain_result == emitting_result, "注入事件源不得改变返回值"
        assert emitter.events, "注入后应产生节点事件"
