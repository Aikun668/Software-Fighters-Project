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
    comparison: bool
    sub_type: str  # "overview" | "guide"
    current_section: str
    stage: str
    content_blocks: list[dict]
    blocks: list[dict]
    response: str
    repair_instructions: list[str]
    previous_blocks: list[dict]


class ContentAgent(BaseAgent):
    """内容生成 Agent —— 生成课程文档、代码案例、思维导图等"""

    def __init__(self, config=None, use_mock_llm: bool = False,
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

    async def plan_outline(self, topic: str, student_profile: dict | None = None) -> dict:
        """公开 API：规划内容大纲。供 ResourceGenWorkflow / LearningPathWorkflow 调用。"""
        state: ContentState = {
            "topic": topic,
            "student_profile": student_profile or {},
        }
        return await self._plan_node(state)

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
        doc_type = state.get("sub_type", "overview")
        doc_label = "技术速览" if doc_type == "overview" else "实战攻略"
        intent = f"{doc_label}：{topic}，覆盖 {len(concepts)} 个关键点"

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
    def _validate_sections(result: dict) -> list[str]:
        """验证 overview sections 结构完整性"""
        issues = []
        sections = result.get("sections", [])
        if not isinstance(sections, list) or len(sections) == 0:
            issues.append("sections 必须是非空数组")
            return issues
        for i, sec in enumerate(sections):
            if not isinstance(sec.get("heading"), str) or not sec["heading"]:
                issues.append(f"sections[{i}] 缺少或 heading 为空")
        return issues

    @staticmethod
    def _validate_outline(result: dict) -> list[str]:
        """验证旧版 outline 结构完整性（向后兼容）"""
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
        """规划内容大纲 — 按 sub_type 路由到不同 prompt"""
        topic = state.get("topic", "")
        sub_type = state.get("sub_type", "overview")
        student_profile = state.get("student_profile", {})

        # 确认 sub_type
        if sub_type not in ("overview", "guide"):
            sub_type = "overview"

        # 路由 prompt 文件
        if sub_type == "guide":
            prompt_file = "guide.yaml"
            expected_key = "steps"
            fallback_outline = {
                "scenario": f"实现{topic}的完整流程。",
                "prerequisites": ["基础编程能力"],
                "steps": [
                    {"heading": "环境准备", "code": "", "explanation": "安装依赖"},
                    {"heading": "核心实现", "code": "", "explanation": f"编写{topic}的核心代码"},
                    {"heading": "验证测试", "code": "", "explanation": "运行并验证结果"},
                ],
                "pitfalls": ["注意输入数据格式"],
                "key_takeaway": f"掌握{topic}的实战实现方法。",
            }
            validator = None
        else:
            prompt_file = "overview.yaml"
            expected_key = "sections"
            fallback_outline = {
                "intro": f"{topic}核心技术解析。",
                "sections": [
                    {"heading": f"{topic}核心概念", "focus": f"理解{topic}的基本原理"},
                    {"heading": f"{topic}关键技术点", "focus": f"掌握{topic}的关键技术"},
                    {"heading": f"{topic}实践要点", "focus": f"{topic}的应用注意事项"},
                ],
                "key_takeaway": f"快速理解{topic}的核心概念和技术要点。",
            }
            validator = self._validate_sections

        outline_prompt = self._load_extra_prompt(
            filename=prompt_file, key="system"
        )
        user_prompt = self._load_extra_prompt(
            filename=prompt_file, key="user_template"
        )
        user_filled = interpolate_variables(
            user_prompt,
            {
                "topic": topic,
                "knowledge_context": "",
            },
        )

        try:
            outline_result = await self._call_llm_json(
                system_prompt=outline_prompt,
                user_prompt=user_filled,
                expected_key=expected_key,
                fallback={},
                validator=validator,
                llm=self.plan_llm,
            )
            items = outline_result.get(expected_key, [])
            if items:
                outline = outline_result
            else:
                raise ValueError(f"Outline has empty {expected_key}")
        except ValueError as e:
            logger.error(f"Content plan failed ({sub_type}): {e}")
            outline = fallback_outline

        return {"outline": outline, "sub_type": sub_type, "stage": "planned"}

    @staticmethod
    def _build_repair_context(repair_instructions: list[str], previous_blocks: list[dict]) -> str:
        """把修复建议与原草稿拼成注入 LLM prompt 的上下文。"""
        if not repair_instructions:
            return ""
        lines = ["[修复要求] 请根据以下修复建议修订内容（在原始草稿基础上修改，而非从零重写）："]
        for i, ins in enumerate(repair_instructions, 1):
            lines.append(f"{i}. {ins}")
        if previous_blocks:
            lines.append("\n原始草稿（参考）：")
            for b in previous_blocks:
                if isinstance(b, dict):
                    heading = b.get("heading", "")
                    content = b.get("content", "")
                    lines.append(f"## {heading}\n{content}")
        return "\n".join(lines)

    async def _generate_node(self, state: ContentState) -> dict:
        """生成内容块 — 按 sub_type 走不同生成路径"""
        topic = state.get("topic", "")
        outline = state.get("outline", {})
        sub_type = state.get("sub_type", "overview")
        student_profile = state.get("student_profile", {})
        comparison = state.get("comparison", False)

        repair_context = self._build_repair_context(
            state.get("repair_instructions") or [],
            state.get("previous_blocks") or [],
        )

        if sub_type == "guide":
            blocks = self._render_guide(topic, outline)
        elif comparison:
            blocks = await self._generate_comparison(topic, outline, student_profile, repair_context)
        else:
            blocks = await self._generate_overview(topic, outline, repair_context)

        safe_blocks = self._apply_safety_filter(blocks)

        doc_label = "实战攻略" if sub_type == "guide" else "技术速览"
        response = f"已为您生成「{topic}」的{doc_label}，共 {len(safe_blocks)} 个内容块。"
        return {"blocks": safe_blocks, "response": response, "stage": "generated"}

    async def _generate_overview(self, topic: str, outline: dict, repair_context: str = "") -> list[dict]:
        """技术速览 — 按 sections 逐块展开"""
        sections = outline.get("sections", [])
        intro = outline.get("intro", f"{topic}技术解析")

        blocks = []
        blocks.append({"type": "section", "heading": "概述", "content": intro})

        sys_prompt = self._load_extra_prompt("overview.yaml", key="system")
        user_tpl = self._load_extra_prompt("overview.yaml", key="user_template")

        for i, sec in enumerate(sections):
            heading = sec.get("heading", f"第{i+1}节")
            focus = sec.get("focus", topic)

            user_prompt = interpolate_variables(
                user_tpl,
                {"topic": topic, "knowledge_context": focus},
            )
            if repair_context:
                user_prompt = user_prompt + "\n\n" + repair_context

            try:
                result = await self._call_llm_json(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    expected_key="sections",
                    fallback={},
                )
                content = self._render_section_content(heading, focus, result)
            except Exception:
                logger.exception(f"Section generation failed for '{heading}'")
                content = f"## {heading}\n\n{focus}相关技术要点。"
            blocks.append({"type": "section", "heading": heading, "content": content})

        key_takeaway = outline.get("key_takeaway", "")
        if key_takeaway:
            blocks.append({"type": "callout", "heading": "核心要点", "content": key_takeaway})
        return blocks

    async def _generate_comparison(self, topic: str, outline: dict, student_profile: dict, repair_context: str = "") -> list[dict]:
        """对比分析文档 — 保留原有逻辑"""
        subsections = outline.get("subsections", [])
        intro = outline.get("intro", f"{topic}对比分析")

        profile_text = self._format_profile(student_profile)
        comparison_instructions = self._load_comparison_template()

        blocks = []
        blocks.append({"type": "section", "heading": "概述", "content": intro})

        sys_prompt = self._load_extra_prompt("outline.yaml", key="system")
        user_tpl = self._load_extra_prompt("outline.yaml", key="user_template")

        if comparison_instructions:
            sys_prompt = sys_prompt + "\n\n" + comparison_instructions

        for i, sub in enumerate(subsections):
            heading = sub.get("heading", f"第{i+1}节")
            role = sub.get("role", "core")
            focus = sub.get("focus", topic)

            user_prompt = interpolate_variables(
                user_tpl,
                {
                    "topic": topic, "topic_summary": focus,
                    "objectives": f"掌握{heading}", "focus_topic": heading,
                    "knowledge_context": "", "student_profile": profile_text,
                },
            )
            if repair_context:
                user_prompt = user_prompt + "\n\n" + repair_context

            try:
                result = await self._call_llm_json(
                    system_prompt=sys_prompt, user_prompt=user_prompt,
                    expected_key="subsections", fallback={},
                )
                content = self._render_block_content(role, heading, focus, topic,
                    result, f"## {heading}\n\n{focus}\n\n{topic}的核心知识点。")
            except Exception:
                logger.exception(f"Block generation failed for '{heading}'")
                content = f"## {heading}\n\n{focus}\n\n{topic}的核心知识点。"
            blocks.append({"type": "section", "heading": heading, "content": content})

        key_takeaway = outline.get("key_takeaway", f"掌握{topic}的对比要点。")
        blocks.append({"type": "callout", "heading": "对比要点", "content": key_takeaway})
        return blocks

    def _render_guide(self, topic: str, outline: dict) -> list[dict]:
        """实战攻略 — plan 已给出完整内容，直接格式化"""
        blocks = []

        scenario = outline.get("scenario", "")
        if scenario:
            blocks.append({"type": "section", "heading": "场景", "content": scenario})

        prerequisites = outline.get("prerequisites", [])
        if prerequisites:
            prereq_text = "\n".join(f"- {p}" for p in prerequisites)
            blocks.append({"type": "callout", "heading": "前置准备", "content": prereq_text})

        steps = outline.get("steps", [])
        for s in steps:
            heading = s.get("heading", "")
            code = s.get("code", "")
            explanation = s.get("explanation", "")
            if code:
                blocks.append({"type": "code", "heading": heading, "content": code})
            if explanation:
                blocks.append({"type": "section", "heading": f"说明：{heading}", "content": explanation})

        pitfalls = outline.get("pitfalls", [])
        if pitfalls:
            pit_text = "\n".join(f"- {p}" for p in pitfalls)
            blocks.append({"type": "callout", "heading": "常见坑点", "content": pit_text})

        key_takeaway = outline.get("key_takeaway", "")
        if key_takeaway:
            blocks.append({"type": "callout", "heading": "核心收获", "content": key_takeaway})
        return blocks

    @staticmethod
    def _render_section_content(heading: str, focus: str, result: dict) -> str:
        """从 overview LLM 输出中提取内容"""
        if not result:
            return f"## {heading}\n\n{focus}"
        intro_text = result.get("intro", "")
        sections = result.get("sections", [])
        if sections:
            lines = []
            if intro_text:
                lines.append(intro_text)
            for s in sections:
                lines.append(f"### {s.get('heading', '')}\n{s.get('focus', '')}")
            return "\n\n".join(lines)
        if intro_text:
            return f"## {heading}\n\n{intro_text}"
        return f"## {heading}\n\n{focus}"

    @staticmethod
    def _load_comparison_template() -> str:
        """加载对比分析模板"""
        try:
            from app.utils.prompt_loader import _resolve_path
            with open(_resolve_path("content_agent/comparison_template.md"), "r", encoding="utf-8") as f:
                comp_raw = f.read()
            import re as _re
            return _re.sub(r'\{\{#if comparison\}\}|\{\{/if\}\}', '', comp_raw).strip()
        except Exception:
            return ""

    @staticmethod
    def _apply_safety_filter(blocks: list[dict]) -> list[dict]:
        """对内容块逐一做安全检查"""
        safe_blocks = []
        for block in blocks:
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
        return safe_blocks

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
