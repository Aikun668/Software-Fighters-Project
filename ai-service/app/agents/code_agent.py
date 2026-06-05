"""CodeAgent — 代码实操案例生成智能体

生成与知识点配套的、可独立运行的代码示例，带分步中文讲解。
难度根据学生画像的 knowledge_base 自适应。
支持 LLM 生成 + 静态 fallback 双路径。
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class CodeState(TypedDict, total=False):
    topic: str
    student_profile: dict
    outline: dict
    whiteboard_context: str
    peer_context: str
    blocks: list[dict]
    response: str


class CodeAgent(BaseAgent):
    """代码实操案例生成 Agent — 输出 code 类型 block"""

    def __init__(self, config=None, use_mock_llm: bool = False,
                 model_profile=None):
        super().__init__(
            agent_name="code_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(CodeState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    @staticmethod
    def _validate_code(result: dict) -> list[str]:
        """验证 code 字段的有效性"""
        issues = []
        code = result.get("code", "")
        if not isinstance(code, str) or len(code.strip()) < 20:
            issues.append("code 字段内容过短（<20 字符），不是有效的代码示例")
        lang = result.get("language", "")
        if not isinstance(lang, str) or not lang:
            issues.append("缺少 language 字段")
        return issues

    async def _generate_node(self, state: CodeState) -> dict:
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        outline = state.get("outline", {})
        whiteboard_context = state.get("whiteboard_context", "")
        peer_context = state.get("peer_context", "")

        # 从大纲中提取与代码相关的 focus
        subsections = outline.get("subsections", [])
        code_related = [s for s in subsections if s.get("role") in ("example", "application")]
        focus = code_related[0].get("focus", topic) if code_related else topic

        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "topic_summary": f"{focus}的代码实操",
                "objectives": f"通过可运行的代码示例掌握{focus}的核心实现",
                "student_profile": self._format_profile(student_profile),
                "whiteboard_context": whiteboard_context,
                "peer_context": peer_context,
            },
        )

        language = "python"
        code = ""
        explanation = ""

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="code",
            fallback={},
            validator=self._validate_code,
        )
        language = result.get("language", "python")
        code = result.get("code", "")
        explanation = result.get("explanation", "")

        content = self._render_content(topic, language, code, explanation)
        heading = f"{topic} 代码示例"

        blocks = [{"type": "code", "heading": heading, "content": content}]

        logger.info(f"CodeAgent generated code ({language}, {len(code)} chars) for topic '{topic}'")
        return {
            "blocks": blocks,
            "response": f"已生成「{topic}」的代码实操案例。",
        }

    def _render_content(self, topic: str, language: str, code: str, explanation: str) -> str:
        """渲染为 Markdown fenced code block + 解释"""
        if code:
            return f"```{language}\n{code}\n```\n\n{explanation}"

        # Fallback
        return (
            f"```python\n"
            f"# {topic} — 代码示例\n"
            f"# 根据你的学习进度自动生成\n\n"
            f"def example():\n"
            f"    \"\"\"关于{topic}的基础示例\"\"\"\n"
            f"    print(\"正在学习: {topic}\")\n"
            f"    # TODO: 在这里添加你感兴趣的具体实现\n\n"
            f"if __name__ == \"__main__\":\n"
            f"    example()\n"
            f"```\n\n"
            f"**代码说明**：\n\n"
            f"以上为基础代码模板。你可以在此基础上扩展具体功能。\n"
            f"建议结合课程文档中的知识点，逐步完善代码实现。\n"
        )
