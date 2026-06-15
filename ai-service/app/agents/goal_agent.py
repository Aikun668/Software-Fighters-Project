import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class GoalState(TypedDict, total=False):
    input: str
    context: str
    student_profile: dict
    goal_title: str
    target_topic: str
    target_level: str
    deadline: str
    motivation: str
    constraints: list[str]
    response: str


class GoalAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="goal_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(GoalState)
        graph.add_node("extract", self._extract_node)
        graph.set_entry_point("extract")
        graph.set_finish_point("extract")
        return graph.compile()

    async def _extract_node(self, state: GoalState) -> dict:
        user_input = state.get("input", "")
        context = state.get("context", "")
        student_profile = state.get("student_profile", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "input": user_input,
                "context": context or "（无额外上下文）",
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="goal_title",
            fallback={},
            validator=self._validate_goal,
            max_retries=1,
        )

        if not result or "goal_title" not in result:
            result = self._fallback_goal(user_input)

        return {
            "goal_title": result.get("goal_title", ""),
            "target_topic": result.get("target_topic", user_input),
            "target_level": result.get("target_level", "understand"),
            "deadline": result.get("deadline", ""),
            "motivation": result.get("motivation", ""),
            "constraints": result.get("constraints", []),
            "response": result.get("response", f"已记录你的学习目标：{result.get('goal_title', user_input)}。"),
        }

    @staticmethod
    def _validate_goal(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("goal_title"), str) or not result["goal_title"]:
            issues.append("goal_title 必须是非空字符串")
        if not isinstance(result.get("target_topic"), str) or not result["target_topic"]:
            issues.append("target_topic 必须是非空字符串")
        return issues

    @staticmethod
    def _fallback_goal(user_input: str) -> dict:
        title = user_input.strip() or "未指定学习目标"
        return {
            "goal_title": title,
            "target_topic": title,
            "target_level": "understand",
            "deadline": "",
            "motivation": "",
            "constraints": [],
            "response": f"已记录你的学习目标：{title}。",
        }
