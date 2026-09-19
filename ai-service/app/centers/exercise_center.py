import asyncio
import logging
from typing import AsyncIterator, Iterator

from app.agents.exercise_agent import ExerciseAgent
from app.centers.schemas import CenterResult, CenterTask
from app.events.types import (
    StreamEvent,
    confidence_event,
    error_content_event,
    flat_done_event,
    progress_content_event,
    steps_event,
    token_event,
)
from app.services.llm_service import PROFILE_EXERCISE

logger = logging.getLogger(__name__)

GENERATE_FAILED_MESSAGE = "题目生成失败，请稍后重试"
SOLVE_FAILED_MESSAGE = "解题功能暂时不可用，请稍后重试"


def _chunks(text: str, size: int) -> Iterator[str]:
    """按固定字数切分文本，与 API 现状的 _sse_stream_chunks 同规则。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


class ExerciseCenter:
    def __init__(
        self,
        exercise_agent: ExerciseAgent | None = None,
        solve_agent=None,
        llm_service=None,
    ):
        self.exercise_agent = exercise_agent
        self.solve_agent = solve_agent
        self.llm_service = llm_service
        # 节流节奏：API 现状 0.3s / 0.5s / 0.03s / 4 字，离线测试注入 0
        self.plan_progress_delay = 0.3
        self.generate_progress_delay = 0.5
        self.token_delay = 0.03
        self.chunk_size = 4

    def _exercise_agent(self) -> ExerciseAgent:
        if self.exercise_agent is None:
            self.exercise_agent = ExerciseAgent(model_profile=PROFILE_EXERCISE)
        return self.exercise_agent

    def _solve_agent_instance(self):
        if self.solve_agent is None:
            from app.agents.solve_agent import SolveAgent
            self.solve_agent = SolveAgent()
        return self.solve_agent

    async def execute(self, task: CenterTask) -> CenterResult:
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        topic = task.params.get("topic") or task.input
        count = task.params.get("count", 3)
        difficulty = task.params.get("difficulty", "medium")

        agent = self._exercise_agent()
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

    async def generate_stream(
        self,
        *,
        topic: str,
        knowledge_node_id: str | None,
        strategy: str,
        count: int,
        difficulty: str,
        student_profile: dict,
    ) -> AsyncIterator[StreamEvent]:
        """出题流：progress(plan) → ExerciseAgent.run → progress(generate) → done(questions)。

        失败路径与现状一致：progress(plan) 已发出，随后 error + done。
        """
        display_topic = knowledge_node_id or topic
        try:
            await asyncio.sleep(self.plan_progress_delay)
            yield progress_content_event("plan", f"正在规划「{display_topic}」的练习题...")

            state = await self._exercise_agent().run({
                "topic": topic,
                "knowledge_node_id": knowledge_node_id,
                "strategy": strategy,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
            })

            await asyncio.sleep(self.generate_progress_delay)
            num_q = len(state.get("questions", []))
            yield progress_content_event("generate", f"已生成 {num_q} 道题目")

            yield flat_done_event({"questions": state.get("questions", [])})
        except Exception as e:
            logger.error(f"Exercise generate stream failed: {e}")
            yield error_content_event(GENERATE_FAILED_MESSAGE)
            yield flat_done_event()

    async def solve_stream(self, *, question: str, context: str) -> AsyncIterator[StreamEvent]:
        """解题流：SolveAgent.run → steps → token* → confidence → done。

        失败路径与现状一致：无前置事件，只有 error + done。
        """
        try:
            state = await self._solve_agent_instance().run({
                "question": question,
                "context": context,
            })

            steps = state.get("steps", [])
            if steps:
                yield steps_event(steps)

            solution = state.get("solution", "")
            if solution:
                for chunk in _chunks(solution, self.chunk_size):
                    await asyncio.sleep(self.token_delay)
                    yield token_event(chunk)

            confidence = state.get("confidence_score")
            if confidence is not None:
                yield confidence_event(confidence)

            yield flat_done_event()
        except Exception as e:
            logger.error(f"Solve stream failed: {e}")
            yield error_content_event(SOLVE_FAILED_MESSAGE)
            yield flat_done_event()
