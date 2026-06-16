import logging

from app.centers.schemas import CenterTask, ExecutionPlan
from app.services.intent_extractor import (
    INTENT_CENTER_MAP,
    _CENTER_EXECUTION_ORDER,
    IntentExtractor,
    IntentResult,
    MultiIntentResult,
)

logger = logging.getLogger(__name__)


class RouterAgent:
    MODE_TO_INTENT: dict[str, str] = {
        "plan": "learning_path",
        "resource": "resource_gen",
        "exercise": "exercise_gen",
        "visualization": "visualize",
    }

    def __init__(self, intent_extractor: IntentExtractor | None = None):
        self.intent_extractor = intent_extractor or IntentExtractor()

    async def route(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 3,
    ) -> ExecutionPlan:
        student_profile = student_profile or {}
        context = context or {}

        if mode != "auto":
            return self._manual_mode_plan(message, mode, student_profile, context)

        multi = await self.intent_extractor.extract_multi(
            message, max_intents=max_intents
        )

        if not multi.is_clear or not multi.intents:
            return ExecutionPlan(
                tasks=[
                    CenterTask(
                        mode="inquiry",
                        intent="inquiry",
                        input=message,
                        params={"question": multi.inquiry_question},
                        context={**context, "student_profile": student_profile},
                    )
                ],
                is_clear=False,
                inquiry_question=multi.inquiry_question,
                intent_meta={"raw_message": message},
            )

        tasks = self._intents_to_tasks(
            multi.intents, message, student_profile, context
        )
        tasks = self._sort_by_execution_order(tasks)

        return ExecutionPlan(
            tasks=tasks,
            is_clear=True,
            intent_meta={"raw_message": message, "intents": [r.intent for r in multi.intents]},
            max_intents=max_intents,
        )

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
        )
        return ExecutionPlan(
            tasks=[task],
            is_clear=True,
            intent_meta={"manual_mode": mode, "raw_message": message},
        )

    def _intents_to_tasks(
        self,
        intents: list[IntentResult],
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
            )
            tasks.append(task)
        return tasks

    def _sort_by_execution_order(self, tasks: list[CenterTask]) -> list[CenterTask]:
        tasks.sort(key=lambda t: _CENTER_EXECUTION_ORDER.get(t.mode, 99))
        for idx, task in enumerate(tasks):
            task.sequence = idx
        return tasks
