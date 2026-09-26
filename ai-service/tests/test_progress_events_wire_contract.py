"""阶段 D 契约：**内部执行事件 → SSE 线上帧**（把"执行过程"变成前端可见）。

背景（《流式系统演进与改造指导》阶段 D）：
> 用户侧并不需要暴露全部内部思考，但可以展示可信、简洁的进度，
> 例如"正在检索课程资料""正在组织解释"。

本轮**最小切片**的边界：
- 把**已经产生**的内部事件（`node.started` / `node.completed`）搬到线上；
- 文案先用占位（节点名），**不做**「节点/事件 → 用户可见文案」映射表（后续再定）；
- **不改**既有帧语义：`token` / `done` / `content` / `center_*` 逐帧不变，只**新增** `progress` 帧。

| 编号 | 断言 |
|---|---|
| `PG-A01` | 内部 `node.started` / `node.completed` → 线上 `progress` 帧（`stage`=节点名，`data.phase` 区分） |
| `PG-A02` | 既有 `token` 帧**逐字且顺序不变**（进度帧不得挤掉/重排 token） |
| `PG-A03` | `done` 仍唯一且为**最后一帧**，进度帧全部早于它 |
| `PG-A04` | `progress` 帧**不带正文**（无 `content` / `response` 键）→ 不会与 token 正文重复渲染 |
| `PG-A05` | 接线是**纯增量**：剔除 `progress` 帧后，与「未接线」基线**逐帧一致** |
| `PG-B01` | `AI_SERVICE_GRAPH_STREAM=0`（硬总闸）→ 不注入事件源、无 `progress` 帧 |

注：本文件用**替身 Center** 驱动（它像真实图那样往注入的事件源发 node 事件），
从而不依赖真实 LLM/图；真实图的 `node.started` 由 `GS-A08` 在转换层锁定。
"""

import json

import pytest

from app.agents.base_agent import current_emitter
from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan
from app.events.stream import ProgressEventType, StreamEmitter
from app.events.types import StreamEvent, StreamEventType

#: 事件源开关（与 `app/events/graph_stream.py::GRAPH_STREAM_ENV` 同名）
GRAPH_STREAM_ENV = "AI_SERVICE_GRAPH_STREAM"


class _StubGraphCenter:
    """替身 Center：像真实图那样往注入的事件源发 node 事件，并逐字回调 on_token。"""

    def __init__(self, chunks: tuple[str, ...] = ("你", "好"), node: str = "step_a"):
        self._chunks = chunks
        self._node = node
        self.emitter_seen: StreamEmitter | None = None

    async def execute(self, task: CenterTask, on_token=None) -> CenterResult:
        emitter = current_emitter.get()
        self.emitter_seen = emitter

        if emitter is not None:
            emitter.emit(
                ProgressEventType.NODE_STARTED,
                node=self._node, namespace=[], depth=0,
            )
        if on_token is not None:
            for chunk in self._chunks:
                await on_token(chunk)
        if emitter is not None:
            emitter.emit(
                ProgressEventType.NODE_COMPLETED,
                node=self._node, namespace=[], depth=0,
            )

        return CenterResult(
            mode=task.mode,
            intent=task.intent,
            event_type="content",
            agent="TutorAgent",
            payload={"response": "你好", "content": "你好"},
            sequence=task.sequence,
        )


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        tasks=[CenterTask(
            mode="auto", intent="tutor_question", input="hi", sequence=0,
        )],
    )


async def _drive() -> tuple[list[StreamEvent], _StubGraphCenter]:
    """跑一遍 `ChatTaskDispatcher.execute`，返回线上帧序列 + 替身 Center。"""
    dispatcher = ChatTaskDispatcher()
    center = _StubGraphCenter()
    dispatcher.auto_center = center
    events = [
        event
        async for event in dispatcher.execute(_plan(), emitter=StreamEmitter())
    ]
    return events, center


def _progress_frames(events: list[StreamEvent]) -> list[StreamEvent]:
    return [e for e in events if e.type is StreamEventType.PROGRESS]


def _frame_signature(event: StreamEvent) -> tuple:
    """帧的**语义指纹**（用于 PG-A05 的逐帧比对）。"""
    data = None if event.data is None else json.dumps(
        event.data, ensure_ascii=False, sort_keys=True,
    )
    return (event.type.value, event.stage, event.message, data)


class TestProgressFramesOnWire:

    @pytest.mark.asyncio
    async def test_pg_a01_node_events_become_progress_frames(self):
        """内部 node 事件 → 线上 `progress` 帧（started / completed 各一帧）。"""
        events, _center = await _drive()

        progress = _progress_frames(events)
        assert progress, "阶段 D：内部节点事件必须出现在 SSE 线上"
        assert [e.stage for e in progress] == ["step_a", "step_a"], (
            f"progress 帧的 stage 应为节点名：{[e.stage for e in progress]}"
        )
        phases = [(e.data or {}).get("phase") for e in progress]
        assert phases == ["started", "completed"], f"应区分开始/完成：{phases}"
        # 占位文案（映射表后续再定）：至少非空，便于前端先展示
        assert all(e.message for e in progress), "progress 帧必须带可展示文案"

    @pytest.mark.asyncio
    async def test_pg_a02_token_frames_unchanged_in_content_and_order(self):
        """既有 token 帧逐字且顺序不变（进度帧不得影响正文流）。"""
        events, _center = await _drive()

        tokens = [
            e.data["content"] for e in events if e.type is StreamEventType.TOKEN
        ]
        assert tokens == ["你", "好"], f"token 内容/顺序被改变：{tokens}"

        # 顺序：token 之间的相对次序保持不变
        kinds = [e.type for e in events]
        assert kinds.count(StreamEventType.TOKEN) == 2

    @pytest.mark.asyncio
    async def test_pg_a03_done_still_unique_and_last(self):
        """`done` 仍唯一且为最后一帧，进度帧全部早于它。"""
        events, _center = await _drive()

        kinds = [e.type for e in events]
        assert kinds.count(StreamEventType.DONE) == 1, "done 必须唯一"
        assert kinds[-1] is StreamEventType.DONE, "done 必须是最后一帧"
        assert max(
            i for i, k in enumerate(kinds) if k is StreamEventType.PROGRESS
        ) < kinds.index(StreamEventType.DONE), "进度帧不得晚于 done"

    @pytest.mark.asyncio
    async def test_pg_a04_progress_frames_carry_no_body_text(self):
        """`progress` 帧不得携带正文键 —— 否则前端会与 token 文本重复渲染。"""
        events, _center = await _drive()

        for event in _progress_frames(events):
            payload = json.loads(event.to_sse().removeprefix("data: ").strip())
            assert payload["type"] == "progress"
            for key in ("content", "response"):
                assert key not in payload, (
                    f"progress 帧混入正文字段 {key!r}：{payload}"
                )

    @pytest.mark.asyncio
    async def test_pg_a05_progress_frames_are_purely_additive(self, monkeypatch):
        """接线是纯增量：剔除进度帧后与「未接线」基线逐帧一致。"""
        monkeypatch.setenv(GRAPH_STREAM_ENV, "0")
        baseline, _ = await _drive()
        baseline_sig = [
            _frame_signature(e) for e in baseline
            if e.type is not StreamEventType.PROGRESS
        ]

        monkeypatch.setenv(GRAPH_STREAM_ENV, "1")
        wired, _ = await _drive()
        wired_sig = [
            _frame_signature(e) for e in wired
            if e.type is not StreamEventType.PROGRESS
        ]

        assert wired_sig == baseline_sig, (
            "除新增 progress 帧外，其余帧必须逐帧不变\n"
            f"基线={baseline_sig}\n接线后={wired_sig}"
        )
        assert _progress_frames(wired), "接线后应出现进度帧"


class TestGraphStreamHardSwitch:

    @pytest.mark.asyncio
    async def test_pg_b01_switch_off_means_no_progress_frames(self, monkeypatch):
        """`AI_SERVICE_GRAPH_STREAM=0` → 不注入事件源（硬总闸），无进度帧。"""
        monkeypatch.setenv(GRAPH_STREAM_ENV, "0")
        events, center = await _drive()

        assert center.emitter_seen is None, "关闭时不得注入事件源"
        assert _progress_frames(events) == [], "关闭时不得出现进度帧"
