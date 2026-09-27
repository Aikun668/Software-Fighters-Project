import logging
from typing import Any

from app.services.plan_service import PlanService

logger = logging.getLogger(__name__)


class AdjustmentAgent:
    def __init__(self, config: dict[str, Any] | None = None, use_mock_llm: bool = False):
        self.config = config or {}
        # 本 Agent 只用纯算法 PlanService，不构造 LLM；保留旗标以统一装配口径
        self.use_mock_llm = use_mock_llm
        self.plan_service = PlanService()

    async def run(self, state: dict) -> dict:
        original_plan = state.get("original_plan", {})
        mastery_vector = state.get("mastery_vector", {})
        days_idle = state.get("days_idle", 0)
        events = state.get("events", [])
        student_profile = state.get("student_profile", {})

        plan_steps = original_plan.get("steps", [])

        paused_steps = [
            {
                "topic": s.get("topic", ""),
                "mastery": mastery_vector.get(s.get("topic", ""), 0.0),
                "topic_difficulty": 3,
            }
            for s in plan_steps
        ]

        decay_results = self.plan_service.soft_landing(paused_steps, days_idle).get("decay_results", {})
        updated_steps = self.plan_service.reorder_plan(
            plan_steps,
            decay_results,
            days_idle,
            user_daily_capacity=original_plan.get("daily_capacity", 3),
        )

        weak_skills = [s for s, m in mastery_vector.items() if m < 0.5]
        added_reviews = []
        if weak_skills:
            added_reviews = [f"强化 {s}" for s in weak_skills[:3]]
            for skill in weak_skills[:2]:
                updated_steps.insert(0, {
                    "day": 1,
                    "topic": skill,
                    "type": "review",
                    "description": f"针对掌握度较低的技能 {skill} 进行复习",
                })

        response = f"已根据你的学习情况调整计划：新增 {len(added_reviews)} 项复习，并重新排列了任务顺序。"

        logger.info(f"AdjustmentAgent: steps={len(plan_steps)} days_idle={days_idle} reviews={len(added_reviews)}")

        return {
            "adjustment_reason": self._build_reason(days_idle, weak_skills),
            "updated_steps": updated_steps,
            "removed_steps": [],
            "added_reviews": added_reviews,
            "response": response,
        }

    @staticmethod
    def _build_reason(days_idle: int, weak_skills: list[str]) -> str:
        parts = []
        if days_idle > 3:
            parts.append(f"已连续 {days_idle} 天未学习，需要 warm-up 复习")
        if weak_skills:
            parts.append(f"存在掌握度不足的技能：{', '.join(weak_skills[:3])}")
        return "；".join(parts) if parts else "根据最新掌握度进行常规微调"
