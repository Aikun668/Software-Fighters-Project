"""StreamEvent type definitions."""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    PROGRESS = "progress"
    ERROR = "error"
    CONTENT = "content"
    DONE = "done"
    CENTER_START = "center_start"
    CENTER_END = "center_end"
    INQUIRY = "inquiry"
    RECOMMENDATION = "recommendation"
    TOKEN = "token"


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
        if self.type is StreamEventType.ERROR:
            # 错误合同：前端 parseSSEStream 与 Java 网关都从 content 键读取
            # 错误信息，只带 message 会让用户看到 "Unknown error"
            payload["content"] = self.message or "处理失败，请稍后重试"
        if self.progress:
            payload["progress"] = round(self.progress, 2)
        if self.data is not None:
            # B1：token 事件把 data 平铺到顶层（前端 case 'token'
            # 直接读 data.content，不在 data.data.content 里找），
            # 其余事件保持原嵌套结构不变。
            if self.type is StreamEventType.TOKEN and isinstance(self.data, dict):
                for k, v in self.data.items():
                    payload[k] = v
            else:
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


def center_start_event(center: str, message: str, sequence: int = 0) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.CENTER_START,
        stage=center,
        message=message,
        data={"sequence": sequence},
    )


def center_end_event(center: str, message: str, sequence: int = 0) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.CENTER_END,
        stage=center,
        message=message,
        data={"sequence": sequence},
    )


def inquiry_event(question: str, suggested_modes: list[str] | None = None) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.INQUIRY,
        message=question,
        data={"suggested_modes": suggested_modes or []},
    )


def knowledge_candidates_event(groups: dict[str, Any]) -> StreamEvent:
    primary = groups.get("primary", [])
    related = groups.get("related", [])
    broad = groups.get("broad", [])
    all_candidates = groups.get("all", primary + related + broad)
    return StreamEvent(
        type=StreamEventType.CONTENT,
        stage="knowledge_graph",
        message="检测到新知识节点候选",
        data={
            "type": "knowledge_graph_candidates",
            "question": "检测到以下新概念，是否加入知识图谱？",
            "primary": primary,
            "related": related,
            "broad": broad,
            "candidates": all_candidates,
        },
    )


def recommendation_event(
    knowledge_node_id: str,
    node_name: str,
    message: str = "",
) -> StreamEvent:
    """SSE 推荐练习事件：聊天中检测到知识点后推送给前端渲染「去练习」按钮。"""
    return StreamEvent(
        type=StreamEventType.RECOMMENDATION,
        stage="exercise",
        message=message or f"检测到知识点「{node_name}」，要去练习一下吗？",
        data={
            "type": "exercise_recommendation",
            "knowledge_node_id": knowledge_node_id,
            "node_name": node_name,
            "action": "add_to_practice",
        },
    )
