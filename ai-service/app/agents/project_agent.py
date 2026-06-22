import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

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
    current_index: int
    all_code: str
    response: str
    blocks: list[dict]


class ProjectAgent(BaseAgent):
    """项目实战 Agent —— 两阶段：设计项目蓝图 → 逐里程碑生成可运行代码。

    LangGraph 图结构：
        design ──→ implement_one ──→ route_next ──┐
                                              ↑     ↓ (还有里程碑)
                                              └─────┘
                                                     ↓ (全部完成)
                                                  assemble → END

    核心模式：条件边循环（conditional edge loop）。每个 implement_one
    调用处理一个里程碑，完成后通过 route_next 判断是继续循环还是进入组装阶段。
    每次循环中，前面阶段的代码通过 all_code 累积传递给下一个里程碑。
    """

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
        graph.add_node("implement_one", self._implement_one_node)
        graph.add_node("assemble", self._assemble_node)

        graph.set_entry_point("design")
        graph.add_edge("design", "implement_one")
        graph.add_conditional_edges(
            "implement_one",
            self._route_next,
            {
                "implement_one": "implement_one",
                "assemble": "assemble",
            },
        )
        graph.add_edge("assemble", END)
        return graph.compile()

    # ── design ─────────────────────────────────────────────

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
            validator=self._validate_design,
            max_retries=1,
        )

        if not result or "project_title" not in result:
            result = self._fallback_design(topic)

        milestones = result.get("milestones", [])
        return {
            "project_title": result.get("project_title", ""),
            "difficulty": result.get("difficulty", "beginner"),
            "description": result.get("description", ""),
            "learning_objectives": result.get("learning_objectives", []),
            "milestones": milestones,
            "tech_stack": result.get("tech_stack", []),
            "time_estimate": result.get("time_estimate", ""),
            "current_index": 0,
            "all_code": "",
            "response": result.get("response", ""),
        }

    @staticmethod
    def _validate_design(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("project_title"), str) or not result["project_title"]:
            issues.append("project_title 必须是非空字符串")
        milestones = result.get("milestones", [])
        if not isinstance(milestones, list) or len(milestones) < 2:
            issues.append("milestones 至少需要 2 个阶段")
        return issues

    # ── route_next（条件边函数）─────────────────────────────

    def _route_next(self, state: ProjectState) -> str:
        current_index = state.get("current_index", 0)
        milestones = state.get("milestones", [])
        if current_index < len(milestones):
            return "implement_one"
        return "assemble"

    # ── implement_one（循环节点，每次处理一个里程碑）────────

    async def _implement_one_node(self, state: ProjectState) -> dict:
        current_index = state.get("current_index", 0)
        milestones = list(state.get("milestones", []))
        all_code = state.get("all_code", "")

        if current_index >= len(milestones):
            return {"current_index": current_index + 1}

        milestone = milestones[current_index]
        step = milestone.get("step", current_index + 1)
        title = milestone.get("title", f"阶段{step}")

        sys_prompt = self._load_extra_prompt("system.yaml", key="implement_system")
        user_tpl = self._load_extra_prompt("system.yaml", key="implement_user")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "project_title": state.get("project_title", ""),
                "description": state.get("description", ""),
                "tech_stack": ", ".join(state.get("tech_stack", ["Python"])),
                "difficulty": state.get("difficulty", "beginner"),
                "step": str(step),
                "milestone_title": title,
                "milestone_goal": milestone.get("goal", ""),
                "milestone_deliverable": milestone.get("deliverable", ""),
                "milestone_hint": milestone.get("hint", ""),
                "previous_code": all_code if all_code else "（这是第一个阶段，没有前面的代码）",
            },
        )

        try:
            result = await self._call_llm_json(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                expected_key="explanation",
                fallback={},
                validator=self._validate_implementation,
                max_retries=1,
            )
        except Exception:
            logger.exception(f"LLM failed for milestone {step}: {title}")
            result = {}

        if not result or "code" not in result:
            result = self._fallback_implementation(milestone, all_code)

        explanation = result.get("explanation", "")
        code = result.get("code", "")
        expected_output = result.get("expected_output", "")

        # 不可变更新：替换当前里程碑
        updated_milestones = list(milestones)
        updated_milestones[current_index] = {
            **milestone,
            "explanation": explanation,
            "code": code,
            "expected_output": expected_output,
        }

        new_all_code = all_code
        if code:
            new_all_code = all_code + f"\n\n# ── 阶段{step}: {title} ──\n{code}"

        logger.info(
            "Milestone %d/%d '%s' done: code=%d chars, explanation=%d chars",
            current_index + 1, len(milestones), title, len(code), len(explanation),
        )

        return {
            "milestones": updated_milestones,
            "current_index": current_index + 1,
            "all_code": new_all_code,
        }

    @staticmethod
    def _validate_implementation(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("code"), str) or len(result.get("code", "")) < 20:
            issues.append("code 必须是非空字符串且至少 20 个字符")
        if not isinstance(result.get("explanation"), str) or not result["explanation"]:
            issues.append("explanation 必须是非空字符串")
        if not isinstance(result.get("expected_output"), str) or not result["expected_output"]:
            issues.append("expected_output 必须是非空字符串")
        return issues

    @staticmethod
    def _fallback_implementation(milestone: dict, _all_code: str) -> dict:
        title = milestone.get("title", "当前阶段")
        goal = milestone.get("goal", "")
        return {
            "explanation": f"本阶段的要点是{goal}。请根据提示逐步实现，注意代码的完整性和可运行性。",
            "code": f"# TODO: 实现「{title}」\n# 目标: {goal}\n\npass",
            "expected_output": f"运行「{title}」的代码后，应该看到与{goal}相关的输出结果。",
        }

    # ── assemble（组装最终输出）──────────────────────────────

    async def _assemble_node(self, state: ProjectState) -> dict:
        topic = state.get("topic", "")
        project_title = state.get("project_title", f"{topic} 微型实践项目")
        milestones = state.get("milestones", [])

        response = state.get("response", "") or f"已为「{topic}」设计并实现微型练习项目，共 {len(milestones)} 个阶段。"

        return {
            "response": response,
            "blocks": [{
                "type": "project",
                "heading": project_title,
                "content": {
                    "title": project_title,
                    "difficulty": state.get("difficulty", "beginner"),
                    "description": state.get("description", ""),
                    "learning_objectives": state.get("learning_objectives", []),
                    "milestones": milestones,
                    "tech_stack": state.get("tech_stack", []),
                    "time_estimate": state.get("time_estimate", ""),
                },
            }],
        }

    # ── fallback ────────────────────────────────────────────

    @staticmethod
    def _fallback_design(topic: str) -> dict:
        return {
            "project_title": f"{topic}微型实践项目",
            "difficulty": "beginner",
            "description": f"通过一个小型项目巩固 {topic} 的核心概念。从需求分析出发，逐步实现一个简单但完整的功能。",
            "learning_objectives": [f"理解{topic}的核心原理", f"能够用代码实现{topic}", "掌握基本的调试与测试方法"],
            "milestones": [
                {"step": 1, "title": "需求分析与设计", "goal": "理解项目需求，设计代码结构",
                 "deliverable": "设计文档", "hint": "先画出流程图或类图，明确输入输出"},
                {"step": 2, "title": "核心功能实现", "goal": "完成核心逻辑编码",
                 "deliverable": "可运行的核心代码", "hint": "先写测试再写实现，聚焦核心逻辑"},
                {"step": 3, "title": "测试与优化", "goal": "验证功能正确性并优化",
                 "deliverable": "通过测试的最终代码", "hint": "考虑边界条件和错误处理"},
            ],
            "tech_stack": ["Python"],
            "time_estimate": "2-4小时",
            "response": f"这是一个基于{topic}的微型练习项目，从设计到实现共 3 个阶段。",
        }
