import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ScheduleState(TypedDict, total=False):
    goal: dict
    decomposition: dict
    student_profile: dict
    existing_plan: dict
    plan_title: str
    estimated_days: int
    daily_capacity: int
    steps: list[dict]
    milestones: list[str]
    response: str


class ScheduleAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="schedule_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ScheduleState)
        graph.add_node("schedule", self._schedule_node)
        graph.set_entry_point("schedule")
        graph.set_finish_point("schedule")
        return graph.compile()

    async def _schedule_node(self, state: ScheduleState) -> dict:
        goal = state.get("goal", {})
        decomposition = state.get("decomposition", {})
        student_profile = state.get("student_profile", {})
        existing_plan = state.get("existing_plan", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "goal": self._format_goal(goal),
                "decomposition": self._format_decomposition(decomposition),
                "student_profile": self._format_profile(student_profile),
                "existing_plan": self._format_existing_plan(existing_plan),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="steps",
            fallback={},
            validator=self._validate_schedule,
            max_retries=1,
        )

        if not result or "steps" not in result:
            result = self._fallback_schedule(goal, decomposition)

        return {
            "plan_title": result.get("plan_title", goal.get("goal_title", "学习计划")),
            "estimated_days": result.get("estimated_days", 7),
            "daily_capacity": result.get("daily_capacity", 3),
            "steps": result.get("steps", []),
            "milestones": result.get("milestones", []),
            "response": result.get("response", "已为你生成学习计划。"),
        }

    @staticmethod
    def _validate_schedule(result: dict) -> list[str]:
        issues = []
        steps = result.get("steps", [])
        if not isinstance(steps, list) or len(steps) == 0:
            issues.append("steps 必须是非空数组")
        return issues

    @staticmethod
    def _format_goal(goal: dict) -> str:
        lines = [f"标题：{goal.get('goal_title', '')}"]
        if goal.get("target_topic"):
            lines.append(f"目标知识点：{goal['target_topic']}")
        if goal.get("target_level"):
            lines.append(f"目标层级：{goal['target_level']}")
        if goal.get("deadline"):
            lines.append(f"截止日期：{goal['deadline']}")
        return "\n".join(lines) if lines else "（暂无目标）"

    @staticmethod
    def _format_decomposition(decomposition: dict) -> str:
        macros = decomposition.get("macro_topics", [])
        micros = decomposition.get("micro_skills", [])
        preqs = decomposition.get("prerequisites", [])
        lines = []
        if macros:
            lines.append("宏观主题：" + "、".join(m.get("name", "") if isinstance(m, dict) else str(m) for m in macros))
        if micros:
            lines.append("微观技能：" + "、".join(m.get("name", "") if isinstance(m, dict) else str(m) for m in micros[:10]))
        if preqs:
            lines.append("前置知识：" + "、".join(p.get("name", "") if isinstance(p, dict) else str(p) for p in preqs))
        return "\n".join(lines) if lines else "（暂无分解结果）"

    @staticmethod
    def _format_existing_plan(existing_plan: dict) -> str:
        steps = existing_plan.get("steps", [])
        if not steps:
            return "（无）"
        return "\n".join(f"Day {s.get('day')}: {s.get('topic')} ({s.get('type')})" for s in steps[:10])

    @staticmethod
    def _fallback_schedule(goal: dict, decomposition: dict) -> dict:
        topic = goal.get("target_topic") or goal.get("goal_title") or "学习目标"
        macros = decomposition.get("macro_topics", [])
        steps = []
        for i, m in enumerate(macros[:5], start=1):
            if not isinstance(m, dict):
                steps.append({
                    "day": i, "topic": str(m), "type": "learn",
                    "description": f"学习{str(m)}",
                    "bloom_level": "understand",
                })
                continue
            steps.append({
                "day": i,
                "topic": m.get("name", topic),
                "type": "learn",
                "description": f"学习{m.get('name', topic)}",
                "bloom_level": m.get("bloom_level", "understand"),
            })
        if not steps:
            steps = [
                {"day": 1, "topic": topic, "type": "learn", "description": f"了解{topic}基础概念", "bloom_level": "understand"},
                {"day": 2, "topic": topic, "type": "exercise", "description": f"练习{topic}应用", "bloom_level": "apply"},
            ]
        else:
            steps.append({
                "day": len(steps) + 1,
                "topic": topic,
                "type": "exercise",
                "description": f"通过练习巩固{topic}",
                "bloom_level": "apply",
            })
        return {
            "plan_title": goal.get("goal_title", f"{topic}学习计划"),
            "estimated_days": len(steps) or 3,
            "daily_capacity": 3,
            "steps": steps,
            "milestones": [f"完成{topic}基础学习"],
            "response": "已基于知识分解生成基础学习计划。",
        }
