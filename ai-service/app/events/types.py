"""StreamEvent type definitions."""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    STAGE_START = "stage_start"    # 阶段开始
    STAGE_END = "stage_end"        # 阶段结束
    PROGRESS = "progress"          # 进度更新
    ERROR = "error"                # 出错
    CONTENT = "content"            # 内容块（逐步推送）
    DONE = "done"                  # 全部完成


@dataclass
class StreamEvent:
    type: StreamEventType
    stage: str = ""           # plan | director | content | mindmap | exercise | reading | code
    message: str = ""         # human-readable: "正在生成课程文档..."
    progress: float = 0.0     # 0.0 ~ 1.0
    data: Any = None          # 附加数据（block, question list 等）

    _metadata: dict = field(default_factory=dict, repr=False)

    def to_sse(self) -> str:
        payload: dict[str, Any] = {
            "type": self.type.value,
        }
        if self.stage:
            payload["stage"] = self.stage
        if self.message:
            payload["message"] = self.message
        if self.progress:
            payload["progress"] = round(self.progress, 2)
        if self.data is not None:
            payload["data"] = self.data
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── convenience factory functions ──────────────────────────────

def stage_start(stage: str, message: str, progress: float = 0.0) -> StreamEvent:
    return StreamEvent(type=StreamEventType.STAGE_START, stage=stage,
                       message=message, progress=progress)

def stage_end(stage: str, message: str, progress: float = 0.0) -> StreamEvent:
    return StreamEvent(type=StreamEventType.STAGE_END, stage=stage,
                       message=message, progress=progress)

def progress_event(stage: str, message: str, progress: float) -> StreamEvent:
    return StreamEvent(type=StreamEventType.PROGRESS, stage=stage,
                       message=message, progress=progress)

def error_event(stage: str, message: str) -> StreamEvent:
    return StreamEvent(type=StreamEventType.ERROR, stage=stage, message=message)

def content_event(data: Any) -> StreamEvent:
    return StreamEvent(type=StreamEventType.CONTENT, data=data)

def done_event(data: Any = None) -> StreamEvent:
    return StreamEvent(type=StreamEventType.DONE, data=data)
