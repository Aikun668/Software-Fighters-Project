import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.analogy_library import get_analogy_library
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class LayeredExplainState(TypedDict, total=False):
    topic: str
    context: str
    student_profile: dict
    code_language: str
    intuition_layer: dict
    formal_layer: dict
    code_layer: dict
    synthesis: str
    response: str


class LayeredExplainAgent(BaseAgent):
    """三层讲解 Agent — 直觉层、形式化层、代码层递进式讲解。"""

    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="layered_explain_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )
        self._analogy_lib = get_analogy_library()

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(LayeredExplainState)
        graph.add_node("explain", self._explain_node)
        graph.set_entry_point("explain")
        graph.set_finish_point("explain")
        return graph.compile()

    async def _explain_node(self, state: LayeredExplainState) -> dict:
        topic = state.get("topic", "")
        context = state.get("context", "")
        student_profile = state.get("student_profile", {})
        code_language = state.get("code_language", "python")

        analogy = self._analogy_lib.format_for_prompt(topic, domain="ai")
        if analogy:
            context = f"{context}\n\n可参考的类比素材：{analogy}".strip()

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "context": context or "（无额外上下文）",
                "student_profile": self._format_profile(student_profile),
                "code_language": code_language,
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="intuition_layer",
            fallback={},
            validator=self._validate_explanation,
            max_retries=1,
        )

        if not result or "intuition_layer" not in result:
            result = self._fallback_explanation(topic, code_language)

        return {
            "intuition_layer": result.get("intuition_layer", {}),
            "formal_layer": result.get("formal_layer", {}),
            "code_layer": result.get("code_layer", {}),
            "synthesis": result.get("synthesis", ""),
            "response": result.get("response", f"已生成「{topic}」的三层讲解。"),
        }

    @staticmethod
    def _validate_explanation(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("intuition_layer"), dict):
            issues.append("intuition_layer 必须是对象")
        if not isinstance(result.get("formal_layer"), dict):
            issues.append("formal_layer 必须是对象")
        return issues

    @staticmethod
    def _fallback_explanation(topic: str, language: str = "python") -> dict:
        return {
            "intuition_layer": {
                "analogy": f"把 {topic} 想象成我们日常生活中熟悉的流程：先输入信息，再按规则处理，最后得到结果。",
                "key_idea": f"{topic} 的核心是把复杂问题拆成可重复执行的步骤。",
            },
            "formal_layer": {
                "definition": f"{topic} 是计算机科学/人工智能中的一个概念，其形式化定义依赖于具体上下文。",
                "formula": "",
                "notes": "注意区分概念的定义、实现与应用场景。",
            },
            "code_layer": {
                "description": f"一个最简 {topic} 示例",
                "language": language,
                "code": f"# {topic} 基础示例\ndef demo():\n    print('正在学习: {topic}')\n\nif __name__ == '__main__':\n    demo()\n",
            },
            "synthesis": f"直觉层帮助建立对 {topic} 的形象认知，形式化层给出准确定义，代码层则展示如何落地实现。",
            "response": f"已为你生成「{topic}」的三层讲解。",
        }
