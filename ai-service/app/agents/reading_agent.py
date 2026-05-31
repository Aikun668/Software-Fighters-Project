"""ReadingAgent — 拓展阅读推荐智能体

根据知识点和学生兴趣方向，生成个性化的拓展阅读推荐（含来源引用）。
支持 LLM 生成 + 静态 fallback 双路径。
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ReadingState(TypedDict, total=False):
    topic: str
    student_profile: dict
    whiteboard_context: str
    peer_context: str
    blocks: list[dict]
    response: str


class ReadingAgent(BaseAgent):
    """拓展阅读推荐 Agent — 输出 reading 类型 block"""

    def __init__(self, config=None, use_mock_llm: bool = True,
                 model_profile=None):
        super().__init__(
            agent_name="reading_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ReadingState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    @staticmethod
    def _validate_suggestions(result: dict) -> list[str]:
        """验证 suggestions 字段的结构完整性"""
        issues = []
        suggestions = result.get("suggestions", [])
        if not isinstance(suggestions, list) or len(suggestions) < 2:
            issues.append("suggestions 必须包含至少 2 条推荐")
            return issues
        for i, s in enumerate(suggestions):
            if not isinstance(s.get("topic"), str) or not s["topic"]:
                issues.append(f"suggestions[{i}] 缺少或 topic 为空")
        return issues

    async def _generate_node(self, state: ReadingState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        whiteboard_context = state.get("whiteboard_context", "")
        peer_context = state.get("peer_context", "")

        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "topic_summary": f"{topic}的拓展应用与前沿发展",
                "objectives": f"了解{topic}的实际应用场景和进阶方向",
                "student_profile": self._format_profile(student_profile),
                "whiteboard_context": whiteboard_context,
                "peer_context": peer_context,
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="suggestions",
            fallback={},
            validator=self._validate_suggestions,
        )
        suggestions = result.get("suggestions", [])

        content = self._render_content(topic, suggestions)
        blocks = [{"type": "reading", "heading": "拓展阅读", "content": content}]

        logger.info(f"ReadingAgent generated {len(suggestions)} suggestions for topic '{topic}'")
        return {
            "blocks": blocks,
            "response": f"已为「{topic}」生成 {len(suggestions)} 条拓展阅读推荐。",
        }

    def _render_content(self, topic: str, suggestions: list[dict]) -> str:
        """渲染建议列表为 Markdown"""
        if not suggestions:
            return (
                f"**{topic} 拓展阅读**\n\n"
                f"- **{topic} 入门指南**: 建议从基础教材和在线课程开始学习\n"
                f"- **{topic} 进阶专题**: 关注相关领域的综述论文和前沿博客\n"
                f"- **{topic} 实践项目**: 在 GitHub 上搜索相关开源项目进行实战\n"
            )

        lines = [f"**{topic} 拓展阅读**\n"]
        for s in suggestions:
            topic_name = s.get("topic", "")
            rationale = s.get("rationale", "")
            source = s.get("source", "")
            if source:
                lines.append(f"- **{topic_name}**: {rationale}（📚 {source}）")
            else:
                lines.append(f"- **{topic_name}**: {rationale}")
        return "\n".join(lines)
