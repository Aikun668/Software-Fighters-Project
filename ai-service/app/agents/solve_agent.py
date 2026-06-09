import asyncio
import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 2000
SOLVE_TIMEOUT_SECONDS = 60  # 过长题目截断，防止 prompt 膨胀和 token 浪费


class SolveState(TypedDict, total=False):
    question: str
    context: str
    student_profile: dict
    steps: list[dict]
    solution: str
    confidence_score: float


class SolveAgent(BaseAgent):
    def __init__(self, config=None, use_mock_llm: bool = False, model_profile=None):
        super().__init__(
            agent_name="solve_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self):
        graph = StateGraph(SolveState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("solve", self._solve_node)
        graph.add_node("review", self._review_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "solve")
        graph.add_edge("solve", "review")
        graph.set_finish_point("review")
        return graph.compile()

    async def _plan_node(self, state: SolveState) -> dict:
        question = state.get("question", "")
        context = state.get("context", "")

        # 长度守卫：截断过长输入，防止 prompt 膨胀
        if len(question) > MAX_QUESTION_LENGTH:
            logger.warning("Question truncated from %d to %d chars", len(question), MAX_QUESTION_LENGTH)
            question = question[:MAX_QUESTION_LENGTH] + "..."

        try:
            sys_prompt = self._load_extra_prompt("solve.yaml", key="system_plan")
            user_tpl = self._load_extra_prompt("solve.yaml", key="user_plan")
            user_prompt = interpolate_variables(
                user_tpl, {"question": question, "context": context},
            )

            result = await asyncio.wait_for(
                self._call_llm_json(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    expected_key="steps",
                    fallback={"steps": self._mock_plan(question)},
                ),
                timeout=SOLVE_TIMEOUT_SECONDS,
            )
            return {"steps": result.get("steps", [])}
        except (ConnectionError, RuntimeError, ValueError, asyncio.TimeoutError) as e:
            logger.error(f"Solve plan failed: {e}")
            return {"steps": self._mock_plan(question)}

    async def _solve_node(self, state: SolveState) -> dict:
        steps = state.get("steps", [])
        question = state.get("question", "")
        context = state.get("context", "")
        profile = state.get("student_profile", {})

        try:
            sys_prompt = self._load_extra_prompt("solve.yaml", key="system_solve")
            user_tpl = self._load_extra_prompt("solve.yaml", key="user_solve")
            user_prompt = interpolate_variables(
                user_tpl, {
                    "question": question,
                    "context": context,
                    "steps": json.dumps(steps, ensure_ascii=False),
                    "profile": json.dumps(profile, ensure_ascii=False),
                },
            )

            result = await asyncio.wait_for(
                self._call_llm_json(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    expected_key="solution",
                    fallback={"solution": self._mock_solution(steps, question)},
                ),
                timeout=SOLVE_TIMEOUT_SECONDS,
            )
            return {"solution": result.get("solution", "")}
        except (ConnectionError, RuntimeError, ValueError, asyncio.TimeoutError) as e:
            logger.error(f"Solve execution failed: {e}")
            return {"solution": self._mock_solution(steps, question)}

    async def _review_node(self, state: SolveState) -> dict:
        solution = state.get("solution", "")
        steps = state.get("steps", [])

        try:
            sys_prompt = self._load_extra_prompt("solve.yaml", key="system_review")
            user_tpl = self._load_extra_prompt("solve.yaml", key="user_review")
            user_prompt = interpolate_variables(
                user_tpl, {
                    "steps": json.dumps(steps, ensure_ascii=False),
                    "solution": solution,
                },
            )

            result = await asyncio.wait_for(
                self._call_llm_json(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    expected_key="confidence_score",
                    fallback={"confidence_score": 0.8},
                ),
                timeout=SOLVE_TIMEOUT_SECONDS,
            )
            try:
                conf = float(result.get("confidence_score", 0.8))
            except (ValueError, TypeError):
                conf = 0.8
            return {
                "solution": solution,
                "confidence_score": conf,
                "issues": result.get("issues", []),
                "suggestions": result.get("suggestions", ""),
            }
        except (ConnectionError, RuntimeError, ValueError, asyncio.TimeoutError) as e:
            logger.error(f"Solve review failed: {e}")
            return {
                "solution": solution,
                "confidence_score": 0.8,
                "issues": [],
                "suggestions": "",
            }

    def _mock_plan(self, question: str) -> list[dict]:
        return [
            {"step": 1, "title": "理解题意", "goal": "明确已知条件和求解目标"},
            {"step": 2, "title": "分析概念", "goal": "确定涉及的核心概念和公式"},
            {"step": 3, "title": "逐步求解", "goal": "按照逻辑步骤推导"},
            {"step": 4, "title": "验证结果", "goal": "检验答案的合理性"},
        ]

    def _mock_solution(self, steps: list[dict], question: str) -> str:
        parts = [f"解答：{question}\n"]
        for s in steps:
            parts.append(f"**第{s['step']}步：{s['title']}**")
            parts.append(f"目标：{s['goal']}")
            parts.append("这里进行详细分析和计算...\n")
        return "\n".join(parts)