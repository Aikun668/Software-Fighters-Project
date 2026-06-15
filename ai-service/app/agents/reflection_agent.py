import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ReflectionState(TypedDict, total=False):
    topic: str
    session_summary: str
    context: str
    student_profile: dict
    reflection_questions: list[str]
    key_takeaways: list[str]
    knowledge_gaps: list[str]
    action_plan: dict
    response: str


class ReflectionAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="reflection_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ReflectionState)
        graph.add_node("reflect", self._reflect_node)
        graph.set_entry_point("reflect")
        graph.set_finish_point("reflect")
        return graph.compile()

    async def _reflect_node(self, state: ReflectionState) -> dict:
        topic = state.get("topic", "")
        session_summary = state.get("session_summary", "")
        context = state.get("context", "")
        student_profile = state.get("student_profile", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "session_summary": session_summary or "（暂无表现记录）",
                "context": context or "（无额外上下文）",
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="reflection_questions",
            fallback={},
            validator=self._validate_reflection,
            max_retries=1,
        )

        if not result or "reflection_questions" not in result:
            result = self._fallback_reflection(topic)

        return {
            "reflection_questions": result.get("reflection_questions", []),
            "key_takeaways": result.get("key_takeaways", []),
            "knowledge_gaps": result.get("knowledge_gaps", []),
            "action_plan": result.get("action_plan", {}),
            "response": result.get("response", f"关于「{topic}」的反思已完成。"),
        }

    @staticmethod
    def _validate_reflection(result: dict) -> list[str]:
        issues = []
        questions = result.get("reflection_questions")
        if not isinstance(questions, list) or len(questions) == 0:
            issues.append("reflection_questions 必须是非空数组")
        return issues

    @staticmethod
    def _fallback_reflection(topic: str) -> dict:
        return {
            "reflection_questions": [
                f"用自己的话复述{topic}的核心概念",
                "这个知识点和你之前学过的内容有什么联系？",
                f"在实际项目中，{topic}可以解决什么问题？",
            ],
            "key_takeaways": [],
            "knowledge_gaps": [],
            "action_plan": {"next_topic": topic, "suggested_method": "用习题巩固", "estimated_time": "30分钟"},
            "response": f"回顾一下你对「{topic}」的理解，看看是否有新的发现。",
        }
