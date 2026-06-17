import logging

from app.agents.exercise_agent import ExerciseAgent
from app.centers.schemas import CenterResult, CenterTask
from app.services.llm_service import PROFILE_EXERCISE

logger = logging.getLogger(__name__)


class ExerciseCenter:
    def __init__(self, exercise_agent: ExerciseAgent | None = None):
        self.exercise_agent = exercise_agent

    async def execute(self, task: CenterTask) -> CenterResult:
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        topic = task.params.get("topic") or task.input
        count = task.params.get("count", 3)
        difficulty = task.params.get("difficulty", "medium")

        agent = self.exercise_agent or ExerciseAgent(model_profile=PROFILE_EXERCISE)
        try:
            state = await agent.run({
                "topic": topic,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
                "purpose": task.params.get("purpose", ""),
            })
            return CenterResult(
                mode="exercise",
                intent=task.intent,
                event_type="exercise",
                payload={
                    "type": "exercise",
                    "topic": topic,
                    "count": len(state.get("questions", [])),
                    "questions": state.get("questions", []),
                    "response": state.get("response", ""),
                },
                agent="ExerciseAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"ExerciseCenter failed: {e}")
            return CenterResult(
                mode="exercise",
                intent=task.intent,
                event_type="error",
                error="练习生成失败",
                agent="ExerciseAgent",
                sequence=task.sequence,
            )
