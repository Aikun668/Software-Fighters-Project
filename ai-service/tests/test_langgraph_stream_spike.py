"""流式阶段 C 的**最小实验**（spike）：先量清 LangGraph 1.1.2 能给什么，再动手。

依据《流式系统演进与改造指导》阶段 C：
> 先调研并以最小实验验证当前 LangGraph 版本能提供哪些流：节点更新、状态更新、
> LLM token、工具调用、子图或自定义事件。

本文件把调研结果钉成**可重复执行的断言**（而不是一次性手跑），供 C 阶段后续切片引用。

环境：`langgraph 1.1.2` / `langchain-core 1.2.19`。

| 编号 | 结论 |
|---|---|
| `SP-01` | `stream_mode="updates"` → 逐节点产出 `{节点名: 增量}`（**可用**） |
| `SP-02` | `stream_mode="values"` → 每步产出完整状态快照（**可用**） |
| `SP-03` | `stream_mode="custom"` + 节点内 `get_stream_writer()`（**可用**，需节点主动写） |
| `SP-04` | `stream_mode="messages"` → 只有 **LangChain 原生 ChatModel** 的 token 会被捕获；本项目
用的是自研 `OpenAILLM` 包装（节点里手调 `chat_stream()`），**捕获不到** ⚠️ |
| `SP-05` | ✅ **好消息**：手工嵌套 `ainvoke`（本项目现状：Workflow 节点里调 `agent.run()`）
在 `subgraphs=True` 下**内层节点事件可见且带 namespace** —— 不必先重写嵌套方式 |
| `SP-06` | `astream` 与 `ainvoke` 的**终态一致**（可安全共存，回退路径成立） |
"""

from typing import Annotated, TypedDict

import pytest
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph


class _State(TypedDict, total=False):
    text: str
    trace: Annotated[list[str], lambda a, b: [*(a or []), *(b or [])]]


# ── 一个最小图：step_a → step_b ──────────────────────────────────


def _build_simple_graph():
    async def step_a(state: _State) -> dict:
        return {"text": (state.get("text") or "") + "A", "trace": ["a"]}

    async def step_b(state: _State) -> dict:
        return {"text": (state.get("text") or "") + "B", "trace": ["b"]}

    graph = StateGraph(_State)
    graph.add_node("step_a", step_a)
    graph.add_node("step_b", step_b)
    graph.set_entry_point("step_a")
    graph.add_edge("step_a", "step_b")
    graph.add_edge("step_b", END)
    return graph.compile()


class _CustomLlm:
    """模拟本项目的自研 LLM 包装（`app/services/llm_service.py::OpenAILLM`）。

    它不是 LangChain 的 `BaseChatModel`，只是暴露一个 `chat_stream()` 异步生成器 ——
    这正是本项目 token 的来源方式。
    """

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def chat_stream(self, *_args, **_kwargs):
        for chunk in self._chunks:
            yield chunk


# ═══════════════════════════════════════════════════════════════════
# 可用的流模式
# ═══════════════════════════════════════════════════════════════════


class TestAvailableStreamModes:

    @pytest.mark.asyncio
    async def test_sp01_updates_yields_per_node_deltas(self):
        graph = _build_simple_graph()
        chunks = [c async for c in graph.astream({"text": ""}, stream_mode="updates")]

        assert chunks == [
            {"step_a": {"text": "A", "trace": ["a"]}},
            {"step_b": {"text": "AB", "trace": ["b"]}},
        ], f"updates 模式形状变化：{chunks}"

    @pytest.mark.asyncio
    async def test_sp02_values_yields_full_state_snapshots(self):
        graph = _build_simple_graph()
        snapshots = [c async for c in graph.astream({"text": ""}, stream_mode="values")]

        assert [s["text"] for s in snapshots] == ["", "A", "AB"]
        assert snapshots[-1]["trace"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_sp03_custom_mode_requires_node_side_writer(self):
        """`custom` 模式需要节点内主动 `get_stream_writer().write(...)`。"""

        async def talkative(_state: _State) -> dict:
            writer = get_stream_writer()
            writer({"type": "progress", "message": "正在计算"})
            return {"text": "done", "trace": ["talkative"]}

        graph = StateGraph(_State)
        graph.add_node("talkative", talkative)
        graph.set_entry_point("talkative")
        graph.add_edge("talkative", END)
        compiled = graph.compile()

        custom = [
            c async for c in compiled.astream({"text": ""}, stream_mode="custom")
        ]
        assert custom == [{"type": "progress", "message": "正在计算"}]

    @pytest.mark.asyncio
    async def test_sp04_messages_mode_cannot_capture_custom_llm_wrapper(self):
        """⚠️ 关键限制：`messages` 模式抓不到自研 LLM 包装的 token。"""

        llm = _CustomLlm(["反", "向", "传", "播"])

        async def llm_node(_state: _State) -> dict:
            text = ""
            async for chunk in llm.chat_stream([]):
                text += chunk
            return {"text": text, "trace": ["llm"]}

        graph = StateGraph(_State)
        graph.add_node("llm_node", llm_node)
        graph.set_entry_point("llm_node")
        graph.add_edge("llm_node", END)
        compiled = graph.compile()

        message_chunks = [
            c async for c in compiled.astream({"text": ""}, stream_mode="messages")
        ]

        assert message_chunks == [], (
            "若这里不再是空：说明 langgraph 版本或调用方式变了，"
            "C 阶段可以考虑直接用 messages 模式替代现有 token 旁路（需重评）"
        )

    @pytest.mark.asyncio
    async def test_sp05_nested_invoke_is_visible_with_subgraphs_mode(self):
        """✅ **好消息（与预期相反，实测结论）**：手工嵌套 `ainvoke` 的内层节点**可见**。

        本项目现状是「Workflow 节点里直接 `await agent.run()`」= 手工嵌套 `ainvoke`。
        实测：只要外层用 `stream_mode="updates", subgraphs=True`，内层节点事件
        **带 namespace 一起出现在同一条流里** —— 因为内层 `ainvoke` 没有传 config，
        沿用了父级的 stream writer 上下文。

        ⇒ C 阶段**不必先重写嵌套方式**（不用把 Agent 图改成 LangGraph 原生 subgraph），
        就能拿到内层节点事件。这是本 spike 最有价值的发现。
        """
        inner = _build_simple_graph()

        async def outer_node(state: _State) -> dict:
            # 本项目现状：Workflow 节点里直接 await agent.run()（= 内层 ainvoke，不传 config）
            inner_result = await inner.ainvoke({"text": "x"})
            return {"text": inner_result["text"], "trace": ["outer"]}

        outer_graph = StateGraph(_State)
        outer_graph.add_node("outer_node", outer_node)
        outer_graph.set_entry_point("outer_node")
        outer_graph.add_edge("outer_node", END)
        outer = outer_graph.compile()

        chunks = [
            c async for c in outer.astream(
                {"text": ""}, stream_mode="updates", subgraphs=True,
            )
        ]

        # subgraphs=True 时每项形如 (namespace_tuple, 更新字典)
        assert all(isinstance(chunk, tuple) and len(chunk) == 2 for chunk in chunks), chunks
        seen = {(ns, name) for ns, update in chunks for name in update}

        top_level = {name for ns, name in seen if ns == ()}
        nested = {name for ns, name in seen if ns != ()}
        assert "outer_node" in top_level, f"外层节点应在顶层命名空间：{seen}"
        assert {"step_a", "step_b"} <= nested, (
            f"内层节点未随 namespace 出现（若确实如此，C 阶段需改用原生 subgraph）：{seen}"
        )


# ═══════════════════════════════════════════════════════════════════
# 与既有路径的兼容性
# ═══════════════════════════════════════════════════════════════════


class TestStreamVsInvokeEquivalence:

    @pytest.mark.asyncio
    async def test_sp06_astream_final_state_matches_ainvoke(self):
        """`astream` 的终态必须与 `ainvoke` 一致（旧路径可作回退）。"""
        graph = _build_simple_graph()

        invoked = await graph.ainvoke({"text": ""})
        last_value = None
        async for snapshot in graph.astream({"text": ""}, stream_mode="values"):
            last_value = snapshot

        assert last_value["text"] == invoked["text"] == "AB"
        assert last_value["trace"] == invoked["trace"] == ["a", "b"]
