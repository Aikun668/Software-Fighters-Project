"""统一执行事件层（L2 → L3 的第一步）。

对应《流式系统演进与改造指导》**阶段 B「定义最小统一 StreamEvent」**，照其三条原则落地：

- **§2.1 先统一事件，再扩展基础设施**：把 `on_token(chunk)` 的单一语义升级为
  `emit(event)`。本模块只确立事件结构，**不上 EventBus / 消息队列**。
- **§2.2 只生成一次，多个消费者复用同一事件源**：一次 `chat_stream()` 的 chunk 只从
  一处流出，由 `StreamEmitter` 广播；本轮已接两个消费者 —— 既有 SSE pump（逐字不变）
  与 `MessageDeltaCollector`（完整文本对账）。
- **§2.3 Transport 与 Event Model 分开**：本模块**不 import 任何 web 框架**，
  SSE 编码仍由 `app/events/types.py::StreamEvent` 负责。

⚠️ 本模块**不改变任何传输字节**：`emit()` 只通知订阅者，不参与 SSE 帧构造。
前端可见载荷本轮零变化；新增的是**可排序、可关联、可观测**的内部事件轨迹
（`run_id` + 单调 `seq` + 时间戳，对应指导文档 §6-5「一次请求可追溯到统一 run_id」）。

后续增量（不在本切片）：`tool.*` / `retry` / `state.updated` 事件、把 error 分支也接上、
LangGraph 原生 streaming（阶段 C）、取消/背压/重连（阶段 E）。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 内存里保留的事件轨迹上限（防止长流导致无界增长；完整持久化属阶段 E）
DEFAULT_MAX_RETAINED_EVENTS = 200


class ProgressEventType(str, Enum):
    """最小事件集（阶段 B：先从最少几类开始）。

    ⚠️ **`node.*` 与 `center.*` 语义/载荷分离，不得混用**（P2 修复，契约 `EM-B04`）：
    - `node.*`  → **LangGraph 图节点**，载荷 `{node, namespace, depth}`（`graph_stream` 发）；
    - `center.*` → **Center 级任务**，载荷 `{center, sequence[, error]}`（`ChatTaskDispatcher` 发）。
    此前二者共用 `node.*`，同一事件类型承载两种 schema，消费者无法凭类型判读载荷。
    """

    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    CENTER_STARTED = "center.started"
    CENTER_COMPLETED = "center.completed"
    MESSAGE_DELTA = "message.delta"
    ERROR = "error"


@dataclass(frozen=True)
class ProgressEvent:
    """一次执行过程中的单个事件。

    Attributes:
        run_id: 同一次请求（run）内恒定，用于日志关联与前端去重/排序。
        seq: 同一 run 内**单调递增**，从 1 开始；跨消费者可用于去重。
        type: 事件类型（见 `ProgressEventType`）。
        ts: 事件发生时间（默认 `time.monotonic()`，只用于相对耗时）。
        data: 载荷（如 `message.delta` 的 `{"content": "..."}`）。
    """

    run_id: str
    seq: int
    type: ProgressEventType
    ts: float
    data: dict[str, Any] = field(default_factory=dict)


class StreamEmitter:
    """执行事件源：`run_id` + 单调 `seq`，可广播给多个订阅者。

    订阅者（消费者）目前有两类用法：
    - **SSE pump**：不在本类内实现 —— 它继续直接消费原始 chunk（保证字节不变）；
    - **Collector**：`MessageDeltaCollector` 订阅后聚合完整文本用于对账。

    设计约束：
    - **每请求一个实例**（与 P3-B3a「逐请求状态不得挂实例/单例」的约定一致）；
    - 订阅者抛错**不得**影响主流程（记 warning 后继续），与本仓库其余横切逻辑一致。
    """

    def __init__(
        self,
        run_id: str | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_retained_events: int = DEFAULT_MAX_RETAINED_EVENTS,
    ):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._clock = clock
        self._seq = 0
        self._subscribers: list[Callable[[ProgressEvent], None]] = []
        self._events: list[ProgressEvent] = []
        self._max_retained = max_retained_events
        self._dropped = 0

    # ── 消费者管理 ────────────────────────────────────────────────

    def subscribe(self, consumer: Callable[[ProgressEvent], None]) -> None:
        """注册消费者（同步可调用对象；内部异常被隔离）。"""
        self._subscribers.append(consumer)

    # ── 事件发射 ─────────────────────────────────────────────────

    def emit(self, event_type: ProgressEventType, **data: Any) -> ProgressEvent:
        """发射一个事件：分配序号 → 留存轨迹 → 广播给全部消费者。"""
        self._seq += 1
        event = ProgressEvent(
            run_id=self.run_id,
            seq=self._seq,
            type=ProgressEventType(event_type),
            ts=self._clock(),
            data=dict(data),
        )
        self._retain(event)
        for consumer in list(self._subscribers):
            try:
                consumer(event)
            except Exception:
                logger.warning(
                    "stream subscriber failed (run_id=%s seq=%s)",
                    self.run_id, event.seq, exc_info=True,
                )
        return event

    async def on_token(self, chunk: str) -> None:
        """**兼容适配**：旧的 `on_token(chunk)` 语义 → `message.delta` 事件。

        签名保持 `async def`，可直接替换既有 `_on_token` 回调。
        """
        self.emit(ProgressEventType.MESSAGE_DELTA, content=chunk)

    # ── 轨迹 ─────────────────────────────────────────────────────

    def _retain(self, event: ProgressEvent) -> None:
        if len(self._events) < self._max_retained:
            self._events.append(event)
        else:
            # 超出上限：只在计数上体现，避免长流无界增长
            self._dropped += 1

    @property
    def events(self) -> list[ProgressEvent]:
        """已保留的事件轨迹（只读快照）。"""
        return list(self._events)

    @property
    def seq(self) -> int:
        """已发射的事件总数（含未留存的）。"""
        return self._seq

    @property
    def dropped_events(self) -> int:
        """因超出留存上限而未保留轨迹的事件数。"""
        return self._dropped


class MessageDeltaCollector:
    """Collector / Reducer：把 `message.delta` 聚合回**完整文本**。

    用途（指导文档 §2.2 / §6-3）：让"前端最终展示的文本"与"后台收集到的完整文本"
    可以逐字对账；同时是将来替换 collector 语义（`CenterResult` / final state）的落点。
    """

    def __init__(self) -> None:
        self.text = ""
        self.delta_count = 0

    def __call__(self, event: ProgressEvent) -> None:
        if event.type is not ProgressEventType.MESSAGE_DELTA:
            return
        content = event.data.get("content")
        if not isinstance(content, str):
            return
        self.text += content
        self.delta_count += 1

    def __repr__(self) -> str:  # pragma: no cover - 仅调试可读性
        return f"MessageDeltaCollector(deltas={self.delta_count}, chars={len(self.text)})"
