import logging

from app.agents.adjustment_agent import AdjustmentAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.diagnose_agent import DiagnoseAgent
from app.agents.exercise_agent import ExerciseAgent
from app.agents.goal_agent import GoalAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.schedule_agent import ScheduleAgent
from app.agents.content_agent import ContentAgent
from app.centers.auto_center import AutoCenter
from app.centers.exercise_center import ExerciseCenter
from app.centers.plan_center import PlanCenter
from app.centers.resource_center import ResourceCenter
from app.centers.result_agent import ResultAgent
from app.centers.router_agent import RouterAgent
from app.centers.schemas import ExecutionPlan
from app.centers.visualization_center import VisualizationCenter
from app.services.intent_extractor import IntentExtractor
from app.services.llm_service import (
    PROFILE_DIAGNOSE,
    PROFILE_EXERCISE,
    PROFILE_STUDENT,
)

logger = logging.getLogger(__name__)


class ChatCenter:
    def __init__(
        self,
        router_agent: RouterAgent | None = None,
        result_agent: ResultAgent | None = None,
    ):
        self.router_agent = router_agent
        self.result_agent = result_agent

    def _get_router(self) -> RouterAgent:
        if self.router_agent is None:
            self.router_agent = RouterAgent(intent_extractor=IntentExtractor())
        return self.router_agent

    def _get_result(self) -> ResultAgent:
        if self.result_agent is None:
            decompose = DecomposeAgent()
            goal = GoalAgent()
            schedule = ScheduleAgent()
            adjustment = AdjustmentAgent()
            diagnose = DiagnoseAgent(model_profile=PROFILE_DIAGNOSE)
            profile = ProfileAgent(model_profile=PROFILE_STUDENT)
            exercise = ExerciseAgent(model_profile=PROFILE_EXERCISE)
            content = ContentAgent()

            self.result_agent = ResultAgent(
                auto_center=AutoCenter(
                    diagnose_agent=diagnose,
                    profile_agent=profile,
                ),
                plan_center=PlanCenter(
                    goal_agent=goal,
                    decompose_agent=decompose,
                    schedule_agent=schedule,
                    adjustment_agent=adjustment,
                ),
                resource_center=ResourceCenter(
                    content_agent=content,
                ),
                exercise_center=ExerciseCenter(
                    exercise_agent=exercise,
                ),
                visualization_center=VisualizationCenter(),
            )
        return self.result_agent

    async def route(
        self,
        message: str,
        mode: str = "auto",
        student_profile: dict | None = None,
        context: dict | None = None,
        max_intents: int = 3,
    ) -> ExecutionPlan:
        router = self._get_router()
        return await router.route(
            message=message,
            mode=mode,
            student_profile=student_profile,
            context=context,
            max_intents=max_intents,
        )

    async def execute(self, plan: ExecutionPlan):
        result = self._get_result()
        async for event in result.execute(plan):
            yield event
