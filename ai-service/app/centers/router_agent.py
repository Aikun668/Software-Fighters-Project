import logging
import os

from app.centers.schemas import CenterTask, ExecutionPlan
from app.services.intent_extractor import (
    INTENT_CENTER_MAP,
    _CENTER_EXECUTION_ORDER,
    INTENT_REGISTRY,
    IntentExtractor,
    _mock_extract_params,
    _score_intent,
)

logger = logging.getLogger(__name__)

# 低门槛：关键词命中即可进入评分
_KEYWORD_FLOOR = 0.3
# 高门槛：置信度达标才保留为独立意图
_CONFIDENCE_THRESHOLD = 0.4
# 超过此数量触发确认卡
_CONFIRM_THRESHOLD = 3


class RouterAgent:
    MODE_TO_INTENT: dict[str, str] = {
        "plan": "learning_path",
        "resource": "resource_gen",
        "exercise": "exercise_gen",
        "visualization": "visualize",
    }

    def __init__(self, intent_extractor: IntentExtractor | None = None):
        self.intent_extractor = intent_extractor or IntentExtractor()
        self._use_llm = os.getenv("INTENT_USE_LLM", "").strip().lower() in ("1", "true", "yes")

    async def route(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 5,
    ) -> ExecutionPlan:
        student_profile = student_profile or {}
        context = context or {}

        if mode != "auto":
            return self._manual_mode_plan(message, mode, student_profile, context)

        tasks = self._keyword_route(message, student_profile, context)
        if tasks:
            tasks = self._sort_by_confidence(tasks)
            needs_confirm = len(tasks) >= _CONFIRM_THRESHOLD
            return ExecutionPlan(
                tasks=tasks,
                is_clear=True,
                needs_confirmation=needs_confirm,
                intent_meta={
                    "raw_message": message,
                    "intents": [t.intent for t in tasks],
                    "confidence": [t.confidence for t in tasks],
                    "strategy": "keyword",
                    "needs_confirmation": needs_confirm,
                },
                max_intents=max_intents,
            )

        task = CenterTask(
            mode="auto",
            intent="tutor_question",
            input=message,
            params={"question": message.strip()},
            context={**context, "student_profile": student_profile},
            confidence=0.0,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"raw_message": message, "strategy": "fallback_tutor"},
        )

    def _keyword_route(
        self,
        message: str,
        student_profile: dict,
        context: dict,
    ) -> list[CenterTask] | None:
        scored = []
        for intent_def in INTENT_REGISTRY:
            score = _score_intent(message, intent_def)
            if score >= _KEYWORD_FLOOR:
                scored.append((score, intent_def))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])

        from app.services.intent_extractor import _MUTEX_GROUPS
        filtered = list(scored)
        for group in _MUTEX_GROUPS:
            matched = [(s, d) for s, d in filtered if d.intent in group]
            if len(matched) > 1:
                best_intent = max(matched, key=lambda x: x[0])[1].intent
                filtered = [(s, d) for s, d in filtered
                            if d.intent not in group or d.intent == best_intent]

        # 置信度阈值过滤（替代硬截断），至少保留 1 个
        qualified = [(s, d) for s, d in filtered if s >= _CONFIDENCE_THRESHOLD]
        if not qualified:
            qualified = [max(filtered, key=lambda x: x[0])]

        tasks: list[CenterTask] = []
        for idx, (score, intent_def) in enumerate(qualified):
            center = INTENT_CENTER_MAP.get(intent_def.intent, "auto")
            params = _mock_extract_params(intent_def.intent, message)
            task = CenterTask(
                mode=center,
                intent=intent_def.intent,
                input=message,
                params=params,
                context={**context, "student_profile": student_profile},
                sequence=idx,
                confidence=score,
            )
            tasks.append(task)

        return tasks

    def _manual_mode_plan(
        self,
        message: str,
        mode: str,
        student_profile: dict,
        context: dict,
    ) -> ExecutionPlan:
        intent = self.MODE_TO_INTENT.get(mode, "tutor_question")
        center = INTENT_CENTER_MAP.get(intent, "auto")
        task = CenterTask(
            mode=center,
            intent=intent,
            input=message,
            params={"question": message, "topic": message},
            context={**context, "student_profile": student_profile, "manual_mode": mode},
            confidence=1.0,
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"manual_mode": mode, "raw_message": message},
        )

    def _intents_to_tasks(
        self,
        intents,
        message: str,
        student_profile: dict,
        context: dict,
    ) -> list[CenterTask]:
        tasks: list[CenterTask] = []
        for idx, result in enumerate(intents):
            center = INTENT_CENTER_MAP.get(result.intent, "auto")
            task = CenterTask(
                mode=center,
                intent=result.intent,
                input=message,
                params=result.params,
                context={**context, "student_profile": student_profile},
                sequence=idx,
                confidence=getattr(result, "confidence", 0.0),
            )
            tasks.append(task)
        return tasks

    def _sort_by_confidence(self, tasks: list[CenterTask]) -> list[CenterTask]:
        tasks.sort(
            key=lambda t: (-t.confidence, _CENTER_EXECUTION_ORDER.get(t.mode, 99))
        )
        for idx, task in enumerate(tasks):
            task.sequence = idx
        return tasks
