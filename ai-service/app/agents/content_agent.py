import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.orchestration.agent_turn_summary import AgentTurnSummary
from app.services.llm_service import create_llm
from app.utils.content_guard import ContentSafetyFilter
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ContentState(TypedDict, total=False):
    topic: str
    student_profile: dict
    outline: dict
    current_section: str
    stage: str
    content_blocks: list[dict]
    response: str


class ContentAgent(BaseAgent):
    """内容生成 Agent —— 生成课程文档、代码案例、思维导图等"""

    def __init__(self, config=None, use_mock_llm: bool = True,
                 model_profile=None):
        super().__init__(
            agent_name="content_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )
        self.use_mock_llm = use_mock_llm
        if not hasattr(self, "plan_llm"):
            self.plan_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)

    def create_turn_summary(
        self, state: dict, output: dict
    ) -> AgentTurnSummary:
        """Override: 利用 ContentAgent 特有的 outline + content_blocks 结构精准提取"""
        topic = state.get("topic", "")

        concepts: list[str] = []
        outline = state.get("outline", {})
        subsections = outline.get("subsections", [])
        for sub in subsections[:8]:
            heading = sub.get("heading", "") if isinstance(sub, dict) else str(sub)
            if heading:
                concepts.append(str(heading))

        if not concepts:
            blocks = output.get("content_blocks") or output.get("blocks") or []
            for b in blocks[:5]:
                heading = b.get("heading") or ""
                if heading:
                    concepts.append(str(heading))

        avoid = list(concepts[:4])
        block_count = len(
            output.get("content_blocks") or output.get("blocks") or []
        )
        intent = f"讲解{topic}的核心概念和原理，覆盖 {len(concepts)} 个知识点"

        return AgentTurnSummary(
            agent_name=self.__class__.__name__,
            topic=topic,
            covered_concepts=concepts[:8],
            generation_intent=intent,
            avoid_duplicating=avoid,
            output_metrics={"block_count": block_count},
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ContentState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.set_finish_point("generate")
        return graph.compile()


    @staticmethod
    def _validate_outline(result: dict) -> list[str]:
        """验证 outline 结构完整性"""
        issues = []
        subsections = result.get("subsections", [])
        if not isinstance(subsections, list) or len(subsections) == 0:
            issues.append("subsections 必须是非空数组")
            return issues
        for i, sub in enumerate(subsections):
            if not isinstance(sub.get("heading"), str) or not sub["heading"]:
                issues.append(f"subsections[{i}] 缺少或 heading 为空")
        return issues

    async def _plan_node(self, state: ContentState) -> dict:
        """规划内容大纲"""
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})

        outline_prompt = self._load_extra_prompt(
            filename="outline.yaml", key="system"
        )
        user_prompt = self._load_extra_prompt(
            filename="outline.yaml", key="user_template"
        )
        user_filled = interpolate_variables(
            user_prompt,
            {
                "topic": topic,
                "topic_summary": f"关于{topic}的知识讲解",
                "objectives": "理解核心概念，掌握基本原理",
                "focus_topic": topic,
                "knowledge_context": "",
                "student_profile": self._format_profile(student_profile),
            },
        )

        try:
            outline_result = await self._call_llm_json(
                system_prompt=outline_prompt,
                user_prompt=user_filled,
                expected_key="subsections",
                fallback={},
                validator=self._validate_outline,
                llm=self.plan_llm,
            )
            subsections = outline_result.get("subsections", [])
            if subsections:
                outline = outline_result
            else:
                raise ValueError("Outline has empty subsections")
        except ValueError as e:
            logger.error(f"Content plan failed: {e}")
            outline = {
                "intro": f"本节介绍{topic}的核心概念。",
                "subsections": [
                    {"heading": f"{topic}基础概念", "role": "core", "focus": topic, "target_words": 300},
                    {"heading": f"{topic}核心原理", "role": "core", "focus": f"{topic}原理", "target_words": 350},
                    {"heading": f"{topic}实践应用", "role": "application", "focus": f"{topic}应用", "target_words": 300},
                ],
                "key_takeaway": f"掌握{topic}的基本原理和应用方法。",
            }

        return {"outline": outline, "stage": "planned"}

    async def _generate_node(self, state: ContentState) -> dict:
        """生成内容块（按 outline.subsections 逐块调用 LLM，按 role 路由子 prompt）"""
        topic = state.get("topic", "")
        outline = state.get("outline", {})
        subsections = outline.get("subsections", [])
        intro = outline.get("intro", f"{topic}介绍")
        student_profile = state.get("student_profile", {})

        content_blocks = []
        content_blocks.append({"type": "section", "heading": "概述", "content": intro})

        profile_text = self._format_profile(student_profile)

        for i, sub in enumerate(subsections):
            heading = sub.get("heading", f"第{i+1}节")
            role = sub.get("role", "core")
            focus = sub.get("focus", topic)

            # 按 role 路由到子 prompt
            sys_prompt, user_tpl, expected_key, block_type, fallback = self._route_block_prompt(
                heading, role, focus, topic
            )

            user_prompt = interpolate_variables(
                user_tpl,
                {
                    "topic": topic,
                    "topic_summary": focus,
                    "objectives": f"掌握{heading}",
                    "focus_topic": heading,
                    "knowledge_context": "",
                    "student_profile": profile_text,
                },
            )

            result = await self._call_llm_json(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                expected_key=expected_key,
                fallback={},
            )

            content = self._render_block_content(role, heading, focus, topic, result, fallback)
            content_blocks.append({"type": block_type, "heading": heading, "content": content})

        # 关键要点
        key_takeaway = outline.get("key_takeaway", f"掌握{topic}的核心原理。")
        content_blocks.append({"type": "callout", "heading": "关键要点", "content": key_takeaway})

        safe_blocks = []
        for block in content_blocks:
            block_text = block.get("content", "")
            block_type = block.get("type", "")
            if block_text and block_type not in ("mindmap", "mermaid"):
                safety_result = ContentSafetyFilter.check(block_text)
                if not safety_result.safe:
                    logger.warning(
                        f"ContentSafety: blocked unsafe content "
                        f"(violations: {safety_result.violations})"
                    )
                    safe_blocks.append({
                        "type": "error",
                        "heading": block.get("heading", "内容块"),
                        "content": "此内容因安全原因已被过滤。",
                    })
                    continue
            safe_blocks.append(block)

        response = f"已为您生成「{topic}」的学习内容，共 {len(safe_blocks)} 个内容块。"
        return {"content_blocks": safe_blocks, "response": response, "stage": "generated"}

    def _route_block_prompt(self, heading: str, role: str, focus: str, topic: str) -> tuple[str, str, str, str, str]:
        """按 subsection role 路由到对应的子 prompt，返回 (sys, user_tpl, expected_key, block_type, fallback)"""
        # 核心内容统一使用 outline.yaml 生成 section 块
        # code/reading/mindmap 已由 CodeAgent/ReadingAgent/MindMapAgent 独立生成
        return (
            self._load_extra_prompt("outline.yaml", key="system"),
            self._load_extra_prompt("outline.yaml", key="user_template"),
            "subsections",
            "section",
            f"## {heading}\n\n{focus}\n\n本节详细讲解{topic}的核心知识点。",
        )

    def _render_block_content(
        self, role: str, heading: str, focus: str, topic: str,
        result: dict, fallback: str,
    ) -> str:
        """从 LLM JSON 输出中提取展示内容（仅处理 section 类型）"""
        if not result:
            return fallback

        intro_text = result.get("intro", "")
        subs = result.get("subsections", [])
        if subs:
            lines = []
            if intro_text:
                lines.append(intro_text)
            for sub in subs:
                lines.append(f"### {sub.get('heading', '')}\n{sub.get('focus', '')}")
            return "\n\n".join(lines)
        if intro_text:
            return f"## {heading}\n\n{intro_text}"
        return fallback
