import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.services.llm_service import create_llm
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_loader import build_prompt, interpolate_variables

logger = logging.getLogger(__name__)


class DeepSolveState(TypedDict, total=False):
    question: str
    context: str
    student_profile: dict
    plan: dict
    investigation: dict
    solution: dict
    verification: dict
    response: str


class DeepSolveWorkflow:
    def __init__(self):
        self.llm = create_llm(temperature=0.1)
        self.graph = self.build_graph()

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(DeepSolveState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("investigate", self._investigate_node)
        graph.add_node("solve", self._solve_node)
        graph.add_node("verify", self._verify_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "investigate")
        graph.add_edge("investigate", "solve")
        graph.add_edge("solve", "verify")
        graph.set_finish_point("verify")
        return graph.compile()

    async def _call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        expected_key: str,
        fallback: dict,
        validator=None,
        max_retries: int = 1,
    ) -> dict:
        last_raw = ""
        for attempt in range(max_retries + 1):
            try:
                messages = [{"role": "user", "content": user_prompt}]
                result_text = await self.llm.chat(messages, system_prompt=system_prompt)
                last_raw = result_text
                result = parse_llm_json(result_text, fallback=fallback, expected_key=expected_key)
                if not isinstance(result, dict):
                    result = fallback

                if result == fallback:
                    if attempt < max_retries:
                        user_prompt = self._append_feedback(
                            user_prompt,
                            f"上一次输出无法解析为包含 '{expected_key}' 的 JSON，请修正。",
                        )
                        logger.warning(f"DeepSolve parse fallback, retrying ({attempt + 1}/{max_retries})")
                    continue

                if validator is not None:
                    issues = validator(result)
                    if issues:
                        if attempt < max_retries:
                            user_prompt = self._append_feedback(
                                user_prompt,
                                "具体问题：\n" + "\n".join(f"  {i + 1}. {issue}" for i, issue in enumerate(issues)),
                            )
                            logger.warning(f"DeepSolve validation failed, retrying ({attempt + 1}/{max_retries})")
                            continue
                        logger.warning(f"DeepSolve validation failed on final attempt: {issues}")

                return result
            except Exception as e:
                logger.error(f"DeepSolve LLM call failed: {e}")
                if attempt < max_retries:
                    logger.info(f"DeepSolve retrying LLM call ({attempt + 1}/{max_retries})")

        logger.error("DeepSolve all LLM attempts failed, returning fallback")
        return fallback

    @staticmethod
    def _append_feedback(original_prompt: str, feedback: str) -> str:
        return f"{original_prompt}\n\n[系统反馈]\n{feedback}\n请根据反馈修正输出。"

    @staticmethod
    def _validate_plan(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("steps"), list) or len(result.get("steps", [])) == 0:
            issues.append("steps 必须是非空数组")
        if not isinstance(result.get("approach"), str) or not result.get("approach"):
            issues.append("approach 必须是非空字符串")
        return issues

    @staticmethod
    def _validate_investigation(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("relevant_concepts"), list) or len(result.get("relevant_concepts", [])) == 0:
            issues.append("relevant_concepts 必须是非空数组")
        return issues

    @staticmethod
    def _validate_solution(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("answer"), str) or not result.get("answer"):
            issues.append("answer 必须是非空字符串")
        if not isinstance(result.get("derivation"), list) or len(result.get("derivation", [])) == 0:
            issues.append("derivation 必须是非空数组")
        return issues

    @staticmethod
    def _validate_verification(result: dict) -> list[str]:
        issues = []
        if not isinstance(result.get("is_valid"), bool):
            issues.append("is_valid 必须是布尔值")
        return issues

    async def _plan_node(self, state: DeepSolveState) -> dict:
        question = state.get("question", "")
        student_profile = state.get("student_profile", {})
        logger.info(f"DeepSolve Plan stage: {question[:80]}")

        know = student_profile.get("knowledge_base", 50)
        sys_prompt = build_prompt("deep_solve", "plan.yaml", key="system")
        user_tpl = build_prompt("deep_solve", "plan.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {"question": question, "knowledge_base": str(know)},
        )

        result = await self._call_llm_json(
            sys_prompt,
            user_prompt,
            "steps",
            {
                "approach": "通用解题策略",
                "steps": ["理解问题", "选择方法", "执行计算", "验证结果"],
                "pitfalls": ["计算错误", "概念混淆"],
            },
            validator=self._validate_plan,
            max_retries=1,
        )
        return {"plan": result}

    async def _investigate_node(self, state: DeepSolveState) -> dict:
        plan = state.get("plan", {})
        question = state.get("question", "")
        context = state.get("context", "")
        logger.info(f"DeepSolve Investigate stage: approach={plan.get('approach', '')[:60]}")

        sys_prompt = build_prompt("deep_solve", "investigate.yaml", key="system")
        user_tpl = build_prompt("deep_solve", "investigate.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "question": question,
                "context": context if context else "无",
                "approach": plan.get("approach", ""),
                "steps": "; ".join(plan.get("steps", [])),
            },
        )

        result = await self._call_llm_json(
            sys_prompt,
            user_prompt,
            "relevant_concepts",
            {
                "findings": ["问题涉及多个概念领域"],
                "relevant_concepts": ["相关概念"],
                "gaps": ["可能存在基础概念不清晰"],
            },
            validator=self._validate_investigation,
            max_retries=1,
        )
        return {"investigation": result}

    async def _solve_node(self, state: DeepSolveState) -> dict:
        question = state.get("question", "")
        plan = state.get("plan", {})
        investigation = state.get("investigation", {})
        logger.info(f"DeepSolve Solve stage: concepts={len(investigation.get('relevant_concepts', []))}")

        sys_prompt = build_prompt("deep_solve", "solve.yaml", key="system")
        user_tpl = build_prompt("deep_solve", "solve.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "question": question,
                "steps": "; ".join(plan.get("steps", [])),
                "concepts": "; ".join(investigation.get("relevant_concepts", [])),
            },
        )

        result = await self._call_llm_json(
            sys_prompt,
            user_prompt,
            "answer",
            {
                "answer": "待推导",
                "derivation": ["分析问题", "选择方法", "执行计算"],
                "key_insights": [],
            },
            validator=self._validate_solution,
            max_retries=1,
        )
        return {"solution": result}

    async def _verify_node(self, state: DeepSolveState) -> dict:
        question = state.get("question", "")
        solution = state.get("solution", {})
        logger.info(f"DeepSolve Verify stage: answer={str(solution.get('answer', ''))[:60]}")

        sys_prompt = build_prompt("deep_solve", "verify.yaml", key="system")
        user_tpl = build_prompt("deep_solve", "verify.yaml", key="user_template")
        derivation = "\n".join(f"  - {d}" for d in solution.get("derivation", []))
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "question": question,
                "answer": solution.get("answer", ""),
                "derivation": derivation,
            },
        )

        result = await self._call_llm_json(
            sys_prompt,
            user_prompt,
            "is_valid",
            {
                "is_valid": True,
                "checks": [],
                "alternative_approach": "",
            },
            validator=self._validate_verification,
            max_retries=1,
        )

        answer = solution.get("answer", "")
        return {
            "verification": result,
            "response": f"解题完成。答案：{answer}。验证：{'通过' if result.get('is_valid') else '需复查'}。",
        }

    async def run(self, state: dict) -> dict:
        return await self.graph.ainvoke(state)
