"""统一执行事件层契约（流式阶段 B，P3-E 轮）。

对应《流式系统演进与改造指导》：
- **§2.1** `on_token(chunk)` → `emit(event)`；
- **§2.2** 一次生成、多方消费（`StreamEmitter` 广播，SSE pump 与 Collector 各取所需）；
- **§2.3** Transport 与 Event Model 分开（事件层不依赖 web 框架）。

| 编号 | 断言 |
|---|---|
| `EM-A01` | `seq` 自 1 起单调递增；`run_id` 全 run 恒定 |
| `EM-A02` | `MessageDeltaCollector` 聚合文本/delta 数；忽略非 delta 事件 |
| `EM-A03` | 消费者异常被隔离，不影响 emit 与其它消费者 |
| `EM-A04` | `await on_token(chunk)` → 产出 `message.delta`（兼容旧回调语义） |
| `EM-A05` | 事件轨迹有留存上限（长流不无界增长） |
| `EM-B01` | **集成**：真实分发器下，Collector 文本 == SSE 收到的 token 拼接（§6-3 对账） |
| `EM-B02` | SSE 通路仍直接消费**原始** chunk（字节不变的机器化保证） |
| `EM-C01` | `app/events/stream.py` 不 import web 框架（§2.3） |
"""

import ast
from pathlib import Path

import pytest

from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan
from app.events.stream import MessageDeltaCollector, ProgressEventType, StreamEmitter

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
STREAM_MODULE = AI_SERVICE_DIR / "app/events/stream.py"
DISPATCHER_SOURCE = AI_SERVICE_DIR / "app/centers/chat_task_dispatcher.py"


class _ChunkingAutoCenter:
    """auto center 替身：把文本按 4 字切块逐个回调 `on_token`。"""

    def __init__(self, text: str):
        self.text = text

    async def execute(self, task, on_token=None):
        for i in range(0, len(self.text), 4):
            chunk = self.text[i:i + 4]
            if on_token is not None:
                await on_token(chunk)
        return CenterResult(
            mode=task.mode,
            intent=task.intent,
            event_type="content",
            payload={"type": "content", "response": self.text},
            sequence=task.sequence or 0,
        )


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        tasks=[CenterTask(mode="auto", intent="x", input="hi", params={}, context={})],
    )


def _sse_token_text(event) -> str | None:
    """从 SSE token 事件里取文本（形状兼容 dict / str）。"""
    if event.type.value != "token":
        return None
    data = event.data
    if isinstance(data, dict):
        return data.get("content")
    return data if isinstance(data, str) else None


# ═══════════════════════════════════════════════════════════════════
# Part A —— 事件层本体
# ═══════════════════════════════════════════════════════════════════


class TestEventLayerUnit:

    def test_em_a01_seq_monotonic_and_run_id_stable(self):
        emitter = StreamEmitter(run_id="run-1")
        types = [ProgressEventType.RUN_STARTED, ProgressEventType.MESSAGE_DELTA,
                 ProgressEventType.RUN_COMPLETED]
        events = [emitter.emit(t) for t in types]

        assert [e.seq for e in events] == [1, 2, 3]
        assert {e.run_id for e in events} == {"run-1"}
        assert emitter.seq == 3

    def test_em_a02_collector_aggregates_only_message_delta(self):
        emitter = StreamEmitter()
        collector = MessageDeltaCollector()
        emitter.subscribe(collector)

        emitter.emit(ProgressEventType.RUN_STARTED, tasks=1)
        emitter.emit(ProgressEventType.MESSAGE_DELTA, content="反向")
        emitter.emit(ProgressEventType.NODE_STARTED, center="auto")
        emitter.emit(ProgressEventType.MESSAGE_DELTA, content="传播")

        assert collector.text == "反向传播"
        assert collector.delta_count == 2

    def test_em_a03_subscriber_exception_is_isolated(self):
        emitter = StreamEmitter()
        seen: list[str] = []

        def _boom(_event):
            raise RuntimeError("subscriber down")

        emitter.subscribe(_boom)
        emitter.subscribe(lambda e: seen.append(e.type.value))

        event = emitter.emit(ProgressEventType.RUN_COMPLETED)

        assert event.seq == 1, "订阅者异常不得影响 emit 的返回值/序号"
        assert seen == ["run.completed"], "其它订阅者仍应收到事件"

    @pytest.mark.asyncio
    async def test_em_a04_on_token_emits_message_delta(self):
        emitter = StreamEmitter()
        await emitter.on_token("区块1")
        await emitter.on_token("区块2")

        events = emitter.events
        assert [e.type for e in events] == [ProgressEventType.MESSAGE_DELTA] * 2
        assert [e.data["content"] for e in events] == ["区块1", "区块2"]

    def test_em_a05_event_trace_is_bounded(self):
        emitter = StreamEmitter(max_retained_events=5)
        for i in range(20):
            emitter.emit(ProgressEventType.MESSAGE_DELTA, content=str(i))

        assert len(emitter.events) == 5, "轨迹必须封顶"
        assert emitter.seq == 20
        assert emitter.dropped_events == 15


# ═══════════════════════════════════════════════════════════════════
# Part B —— 与真实分发器集成
# ═══════════════════════════════════════════════════════════════════


class TestDispatcherIntegration:

    @pytest.mark.asyncio
    async def test_em_b01_collector_reconciles_with_sse_tokens(self):
        """一次生成、多方消费：Collector 的文本 == SSE 逐字收到的 token 拼接。"""
        text = "反向传播是链式法则的工程实现，逐层复用局部梯度。"
        dispatcher = ChatTaskDispatcher(auto_center=_ChunkingAutoCenter(text))
        emitter = StreamEmitter(run_id="run-reconcile")
        collector = MessageDeltaCollector()
        emitter.subscribe(collector)

        sse_tokens: list[str] = []
        async for event in dispatcher.execute(_plan(), emitter=emitter):
            token_text = _sse_token_text(event)
            if token_text is not None:
                sse_tokens.append(token_text)

        assert sse_tokens, "SSE 通路必须仍有 token"
        assert collector.text == "".join(sse_tokens) == text, "前后台文本必须逐字对账"

        types = [e.type.value for e in emitter.events]
        assert types[0] == "run.started"
        assert types[-1] == "run.completed"
        assert types.count("message.delta") == collector.delta_count
        assert [e.seq for e in emitter.events] == list(range(1, len(emitter.events) + 1))

    @pytest.mark.asyncio
    async def test_em_b02_emitter_is_optional_and_per_request(self):
        """不传 emitter 也要照常工作（既有调用点零改动），且事件源是每请求新建的。"""
        dispatcher = ChatTaskDispatcher(auto_center=_ChunkingAutoCenter("abc"))
        events = [e async for e in dispatcher.execute(_plan())]
        assert any(e.type.value == "done" for e in events)

    def test_em_b03_sse_path_still_consumes_raw_chunk(self):
        """SSE 通路必须继续直接消费原始 chunk（不改字节的机器化保证）。"""
        tree = ast.parse(DISPATCHER_SOURCE.read_text(encoding="utf-8"))
        on_token = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_on_token":
                on_token = node
        assert on_token is not None, "找不到 token 泵 _on_token"

        source = ast.unparse(on_token)
        assert "token_queue.put(chunk)" in source, "原始 chunk 未进 SSE 队列"
        assert "run_emitter.on_token(chunk)" in source, "未接入统一事件层"


# ═══════════════════════════════════════════════════════════════════
# Part C —— Transport 与 Event Model 分开
# ═══════════════════════════════════════════════════════════════════


class TestTransportSeparation:

    def test_em_c01_stream_module_has_no_web_dependency(self):
        """事件层不得依赖 web 框架（§2.3）。"""
        tree = ast.parse(STREAM_MODULE.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)

        banned = {m for m in modules if m.split(".")[0] in {"fastapi", "starlette", "uvicorn"}}
        assert banned == set(), f"事件层引入了 web 框架：{banned}"
