import logging

from app.centers.schemas import CenterResult, CenterTask

logger = logging.getLogger(__name__)


class PlanCenter:
    def __init__(
        self,
        path_workflow=None,
        inquiry_service=None,
        goal_agent=None,
        decompose_agent=None,
        schedule_agent=None,
        adjustment_agent=None,
    ):
        self.path_workflow = path_workflow
        self.inquiry_service = inquiry_service
        self.goal_agent = goal_agent
        self.decompose_agent = decompose_agent
        self.schedule_agent = schedule_agent
        self.adjustment_agent = adjustment_agent

    async def execute(self, task: CenterTask) -> CenterResult:
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        user_id = context.get("user_id", 1)
        topic = task.params.get("topic") or task.input

        if task.intent == "adjust_plan" and self.adjustment_agent is not None:
            return await self._run_adjustment(task, student_profile)

        if self.goal_agent is not None and self.schedule_agent is not None:
            return await self._run_new_plan(task, user_id, topic, student_profile)

        return await self._run_legacy_plan(task, user_id, topic, student_profile)

    async def _run_new_plan(
        self,
        task: CenterTask,
        user_id: int,
        topic: str,
        student_profile: dict,
    ) -> CenterResult:
        try:
            goal_state = await self.goal_agent.run({
                "input": task.input,
                "context": task.params.get("context", ""),
                "student_profile": student_profile,
            })
            goal = {
                "goal_title": goal_state.get("goal_title", topic),
                "target_topic": goal_state.get("target_topic", topic),
                "target_level": goal_state.get("target_level", "understand"),
                "deadline": goal_state.get("deadline", ""),
                "motivation": goal_state.get("motivation", ""),
                "constraints": goal_state.get("constraints", []),
            }
        except Exception as e:
            logger.error(f"PlanCenter goal extraction failed: {e}")
            goal = {"goal_title": topic, "target_topic": topic, "target_level": "understand"}

        try:
            decompose_state = await self.decompose_agent.run({
                "topic": goal.get("target_topic", topic),
                "context": task.input,
                "student_profile": student_profile,
            })
            decomposition = {
                "macro_topics": decompose_state.get("macro_topics", []),
                "micro_skills": decompose_state.get("micro_skills", []),
                "prerequisites": decompose_state.get("prerequisites", []),
            }
        except Exception as e:
            logger.error(f"PlanCenter decomposition failed: {e}")
            decomposition = {}

        try:
            schedule_state = await self.schedule_agent.run({
                "goal": goal,
                "decomposition": decomposition,
                "student_profile": student_profile,
                "existing_plan": {},
            })
            steps = schedule_state.get("steps", [])
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="plan",
                payload={
                    "type": "plan",
                    "title": schedule_state.get("plan_title", f"{topic}学习计划"),
                    "topic": topic,
                    "total_steps": len(steps),
                    "steps": steps,
                    "milestones": schedule_state.get("milestones", []),
                    "estimated_days": schedule_state.get("estimated_days", 7),
                    "daily_capacity": schedule_state.get("daily_capacity", 3),
                    "goal": goal,
                    "concept_graph": decomposition,
                    "summary": schedule_state.get("response", ""),
                },
                agent="GoalAgent+DecomposeAgent+ScheduleAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"PlanCenter schedule failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="计划编排失败",
                agent="ScheduleAgent",
                sequence=task.sequence,
            )

    async def _run_adjustment(self, task: CenterTask, student_profile: dict) -> CenterResult:
        try:
            state = await self.adjustment_agent.run({
                "original_plan": task.params.get("original_plan", {}),
                "mastery_vector": task.params.get("mastery_vector", {}),
                "days_idle": task.params.get("days_idle", 0),
                "events": task.params.get("events", []),
                "student_profile": student_profile,
            })
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="plan",
                payload={
                    "type": "plan_adjustment",
                    "adjustment_reason": state.get("adjustment_reason", ""),
                    "updated_steps": state.get("updated_steps", []),
                    "removed_steps": state.get("removed_steps", []),
                    "added_reviews": state.get("added_reviews", []),
                    "summary": state.get("response", ""),
                },
                agent="AdjustmentAgent",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"PlanCenter adjustment failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="计划调整失败",
                agent="AdjustmentAgent",
                sequence=task.sequence,
            )

    async def _run_legacy_plan(
        self,
        task: CenterTask,
        user_id: int,
        topic: str,
        student_profile: dict,
    ) -> CenterResult:
        try:
            from app.services.inquiry_service import InquiryService
            from app.workflows.learning_path import LearningPathWorkflow

            inquiry = self.inquiry_service or InquiryService()
            check_result = await inquiry.check(task.input, student_profile)

            if not check_result.is_clear:
                return CenterResult(
                    mode="plan",
                    intent=task.intent,
                    event_type="inquiry",
                    payload={
                        "type": "inquiry",
                        "is_clear": False,
                        "clarified_topic": check_result.clarified_topic or topic,
                        "questions": check_result.questions,
                        "rationale": check_result.rationale,
                    },
                    agent="InquiryService",
                    sequence=task.sequence,
                )

            workflow = self.path_workflow or LearningPathWorkflow()
            path_state = await workflow.run({
                "user_id": user_id,
                "student_profile": student_profile,
                "topic": topic,
            })

            steps = path_state.get("steps", [])
            concept_graph = path_state.get("concept_graph", {})
            response = path_state.get("response", "")

            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="plan",
                payload={
                    "type": "plan",
                    "title": f"{topic}学习计划",
                    "topic": topic,
                    "total_steps": len(steps),
                    "steps": steps,
                    "concept_graph": concept_graph,
                    "summary": response,
                },
                agent="LearningPathWorkflow",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"PlanCenter failed: {e}")
            return CenterResult(
                mode="plan",
                intent=task.intent,
                event_type="error",
                error="路径规划失败",
                agent="LearningPathWorkflow",
                sequence=task.sequence,
            )
