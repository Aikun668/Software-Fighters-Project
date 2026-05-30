import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.llm_service import create_llm
from app.utils.content_guard import ContentSafetyFilter
from app.utils.mermaid_generator import concept_graph_to_mermaid
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

    def __init__(self, config=None, use_mock_llm: bool = True):
        super().__init__(
            agent_name="content_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm
        self.plan_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ContentState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.set_finish_point("generate")
        return graph.compile()


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
            result = await self.plan_llm.chat(
                [{"role": "user", "content": user_filled}],
                system_prompt=outline_prompt,
            )
            outline = json.loads(result)
            # Fix 3: 借鉴 DeepTutor _json_has_expected 模式：校验关键字段
            if not isinstance(outline.get("subsections"), list) or len(outline.get("subsections", [])) == 0:
                raise ValueError(f"Outline missing subsections, got keys: {list(outline.keys())}")
        except (json.JSONDecodeError, ValueError, ConnectionError, RuntimeError) as e:
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

        # 思维导图
        mindmap_nodes = [{"id": "root", "label": topic}]
        for i, sub in enumerate(subsections):
            mindmap_nodes.append({"id": f"sub_{i}", "label": sub.get("heading", f"第{i+1}节")})
        content_blocks.append({
            "type": "mindmap", "heading": "知识结构",
            "content": json.dumps({
                "nodes": mindmap_nodes,
                "edges": [{"src": "root", "dst": f"sub_{i}"} for i in range(len(subsections))],
            }, ensure_ascii=False),
        })

        # Mermaid 概念图
        concept_graph_input = {
            "nodes": [{"id": n["id"], "label": n["label"]} for n in mindmap_nodes],
            "edges": [{"from": "root", "to": f"sub_{i}", "label": "包含"} for i in range(len(subsections))],
        }
        mermaid_diagram = concept_graph_to_mermaid(concept_graph_input)
        content_blocks.append({
            "type": "mermaid", "heading": "概念关系图",
            "content": mermaid_diagram,
        })

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
        if role == "example":
            return (
                self._load_extra_prompt("code.yaml", key="system"),
                self._load_extra_prompt("code.yaml", key="user_template"),
                "code",
                "code",
                f"# {heading}\n# 示例代码\nprint('示例 - {topic}')",
            )
        elif role in ("comparison", "application"):
            return (
                self._load_extra_prompt("deep_dive.yaml", key="system"),
                self._load_extra_prompt("deep_dive.yaml", key="user_template"),
                "suggestions",
                "callout",
                f"**{heading}**\n\n{focus} 的拓展内容正在准备中。",
            )
        else:
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
        """从 LLM JSON 输出中提取展示内容"""
        if not result:
            return fallback

        if role == "example":
            code = result.get("code", "")
            lang = result.get("language", "python")
            explanation = result.get("explanation", "")
            if code:
                return f"```{lang}\n{code}\n```\n\n{explanation}"
            return fallback

        elif role in ("comparison", "application"):
            suggestions = result.get("suggestions", [])
            if suggestions:
                lines = [f"**{heading}**\n"]
                for s in suggestions:
                    lines.append(f"- **{s.get('topic', '')}**: {s.get('rationale', '')}")
                return "\n".join(lines)
            return fallback

        else:  # core / derivation
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
