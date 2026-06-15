import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ProjectState(TypedDict, total=False):
    topic: str
    prerequisites: str
    student_profile: dict
    project_title: str
    difficulty: str
    description: str
    learning_objectives: list[str]
    milestones: list[dict]
    tech_stack: list[str]
    time_estimate: str
    response: str


class ProjectAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="project_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ProjectState)
        graph.add_node("design", self._design_node)
        graph.set_entry_point("design")
        graph.set_finish_point("design")
        return graph.compile()

    async def _design_node(self, state: ProjectState) -> dict:
        topic = state.get("topic", "")
        prerequisites = state.get("prerequisites", "")
        student_profile = state.get("student_profile", {})

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "prerequisites": prerequisites or "（无记录）",
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="project_title",
            fallback={},
            validator=self._validate_project,
            max_retries=1,
        )

        if not result or "project_title" not in result:
            result = self._fallback_project(topic)

        return {
            "project_title": result.get("project_title", ""),
            "difficulty": result.get("difficulty", "beginner"),
            "description": result.get("description", ""),
            "learning_objectives": result.get("learning_objectives", []),
            "milestones": result.get("milestones", []),
            "tech_stack": result.get("tech_stack", []),
            "time_estimate": result.get("time_estimate", ""),
            "response": result.get("response", f"已为「{topic}」设计微型练习项目。"),
        }

    @staticmethod
    def _validate_project(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("project_title"), str) or not result["project_title"]:
            issues.append("project_title 必须是非空字符串")
        milestones = result.get("milestones", [])
        if not isinstance(milestones, list) or len(milestones) < 2:
            issues.append("milestones 至少需要 2 个阶段")
        return issues

    @staticmethod
    def _fallback_project(topic: str) -> dict:
        return {
            "project_title": f"{topic}微型实践项目",
            "difficulty": "beginner",
            "description": f"通过一个小型项目巩固 {topic} 的核心概念。从需求分析出发，逐步实现一个简单但完整的功能。",
            "learning_objectives": [f"理解{topic}的核心原理", f"能够用代码实现{topic}", "掌握基本的调试与测试方法"],
            "milestones": [
                {"step": 1, "title": "需求分析与设计", "goal": "理解项目需求，设计代码结构", "deliverable": "设计文档", "hint": "画出流程图"},
                {"step": 2, "title": "核心功能实现", "goal": "完成核心逻辑编码", "deliverable": "可运行的代码", "hint": "先写测试再写实现"},
                {"step": 3, "title": "测试与优化", "goal": "验证功能正确性并优化", "deliverable": "通过测试的最终代码", "hint": "考虑边界条件和错误处理"},
            ],
            "tech_stack": ["Python"],
            "time_estimate": "2-4小时",
            "response": f"这是一个基于{topic}的微型练习项目，从设计到实现共 3 个阶段。",
        }
