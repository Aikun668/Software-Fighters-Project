import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class ExerciseVariantState(TypedDict, total=False):
    original_question: dict
    topic: str
    count: int
    strategy: str
    student_profile: dict
    variants: list[dict]
    variant_strategy: str
    response: str


class ExerciseVariantAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="exercise_variant_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ExerciseVariantState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    async def _generate_node(self, state: ExerciseVariantState) -> dict:
        original_question = state.get("original_question", {})
        topic = state.get("topic") or original_question.get("question") or ""
        count = state.get("count", 3)
        strategy = state.get("strategy", "mixed")
        student_profile = state.get("student_profile", {})

        original_json = self._format_question(original_question)

        sys_prompt = self._load_prompt()
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "original_question": original_json,
                "topic": topic,
                "count": str(count),
                "strategy": strategy,
                "student_profile": self._format_profile(student_profile),
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="variants",
            fallback={},
            validator=self._validate_variants,
            max_retries=1,
        )

        if not result or "variants" not in result:
            result = self._fallback_variants(original_question, count)

        variants = result.get("variants", [])
        logger.info(f"ExerciseVariantAgent: generated {len(variants)} variants for '{topic}'")

        return {
            "variants": variants,
            "variant_strategy": result.get("variant_strategy", strategy),
            "response": result.get("response", f"已为「{topic}」生成 {len(variants)} 道变体题目。"),
        }

    @staticmethod
    def _validate_variants(result: dict) -> list[str]:
        issues = []
        variants = result.get("variants")
        if not isinstance(variants, list) or len(variants) == 0:
            issues.append("variants 必须是非空数组")
        return issues

    @staticmethod
    def _format_question(question: dict) -> str:
        import json
        if not question:
            return "（无原题信息）"
        return json.dumps(question, ensure_ascii=False, indent=2)

    @staticmethod
    def _fallback_variants(original_question: dict, count: int) -> dict:
        topic = original_question.get("question", "知识点")
        answer = original_question.get("correct_answer", "")
        variants = []
        for i in range(count):
            variants.append({
                "question_id": f"var_{i + 1}",
                "question_type": original_question.get("question_type", "choice"),
                "question": f"变体 {i + 1}：关于 {topic}，从另一个角度考虑...",
                "options": original_question.get("options", {}),
                "correct_answer": answer,
                "explanation": f"变体 {i + 1} 的解析",
                "difficulty": "medium",
            })
        return {
            "variants": variants,
            "variant_strategy": "mixed",
            "response": f"已生成 {len(variants)} 道基础变体题目。",
        }
