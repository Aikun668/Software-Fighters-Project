from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CenterTask:
    mode: str
    intent: str
    input: str
    params: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    sequence: int = 0
    confidence: float = 0.0
    # T4-B：本任务依赖的上游任务 sequence（仅当真依赖时非空；
    # 执行时由 Dispatcher 把上游 CenterResult 注入 context["upstream_results"]）
    depends_on: list[int] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    tasks: list[CenterTask] = field(default_factory=list)
    intent_meta: dict = field(default_factory=dict)
    is_clear: bool = True
    inquiry_question: str = ""
    max_intents: int = 3
    needs_confirmation: bool = False  # 3+ 意图时推送确认卡

    def __post_init__(self):
        if len(self.tasks) > self.max_intents:
            self.tasks = self.tasks[: self.max_intents]


@dataclass
class CenterResult:
    mode: str
    intent: str
    event_type: str = "content"
    payload: dict = field(default_factory=dict)
    agent: str = ""
    sequence: int = 0
    error: Optional[str] = None
    profile_delta: dict = field(default_factory=dict)


@dataclass
class AggregatedResult:
    results: list[CenterResult] = field(default_factory=list)
    summary: str = ""
    next_steps: list[str] = field(default_factory=list)
    profile_delta: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
