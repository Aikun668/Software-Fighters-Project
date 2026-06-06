"""Deep Solve 工作流骨架 — Plan → Investigate → Solve → Verify

P2 前瞻性设计，答辩 PPT 展示架构演进方向。
当前为骨架实现，四阶段节点定义完整但 LLM 调用待 P2 实现。
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph

logger = logging.getLogger(__name__)


class DeepSolveState(TypedDict, total=False):
    """Deep Solve 工作流状态"""
    question: str                   # 原始问题
    context: str                    # 知识库上下文
    student_profile: dict           # 学生画像
    # Plan 阶段
    plan: dict                      # {"approach": str, "steps": list[str], "pitfalls": list[str]}
    # Investigate 阶段
    investigation: dict             # {"findings": list[str], "relevant_concepts": list[str], "gaps": list[str]}
    # Solve 阶段
    solution: dict                  # {"answer": str, "derivation": list[str], "key_insights": list[str]}
    # Verify 阶段
    verification: dict              # {"is_valid": bool, "checks": list[dict], "alternative_approach": str}
    response: str                   # 最终输出文本


class DeepSolveWorkflow:
    """Deep Solve 四阶段解题工作流。

    阶段：
      1. Plan     — 分析问题类型，规划解题路径，预判常见陷阱
      2. Investigate — 深入调查相关概念、公式、已知条件
      3. Solve    — 执行求解，逐步推导
      4. Verify   — 验证答案正确性，检查边界条件，提供替代解法
    """

    def __init__(self):
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

    # ── 阶段节点（骨架签名，LLM 调用待 P2 实现） ──────────────────

    async def _plan_node(self, state: DeepSolveState) -> dict:
        """【Plan】分析问题类型，规划解题路径。

        P2 实现：LLM 调用 → 返回 approach + steps + pitfalls
        """
        question = state.get("question", "")
        logger.info(f"DeepSolve Plan stage (skeleton): {question[:80]}")

        # P2: 替换为 LLM 调用
        return {
            "plan": {
                "approach": "待 P2 实现",
                "steps": [],
                "pitfalls": [],
            }
        }

    async def _investigate_node(self, state: DeepSolveState) -> dict:
        """【Investigate】深入调查相关概念、公式、已知条件。

        P2 实现：RAG 检索 + LLM 分析 → findings + relevant_concepts + gaps
        """
        plan = state.get("plan", {})
        logger.info(f"DeepSolve Investigate stage (skeleton): approach={plan.get('approach')}")

        # P2: 替换为 LLM + RAG 调用
        return {
            "investigation": {
                "findings": [],
                "relevant_concepts": [],
                "gaps": [],
            }
        }

    async def _solve_node(self, state: DeepSolveState) -> dict:
        """【Solve】执行求解，逐步推导。

        P2 实现：LLM 调用（基于 plan + investigation）→ answer + derivation + key_insights
        """
        investigation = state.get("investigation", {})
        logger.info(
            f"DeepSolve Solve stage (skeleton): concepts={len(investigation.get('relevant_concepts', []))}"
        )

        # P2: 替换为 LLM 调用
        return {
            "solution": {
                "answer": "待 P2 实现",
                "derivation": [],
                "key_insights": [],
            }
        }

    async def _verify_node(self, state: DeepSolveState) -> dict:
        """【Verify】验证答案正确性，检查边界条件，提供替代解法。

        P2 实现：LLM self-critique → is_valid + checks + alternative_approach
        """
        solution = state.get("solution", {})
        logger.info(f"DeepSolve Verify stage (skeleton): answer={solution.get('answer')}")

        # P2: 替换为 LLM self-critique
        return {
            "verification": {
                "is_valid": False,
                "checks": [],
                "alternative_approach": "",
            },
            "response": "[P2 Deep Solve 骨架] 待 LLM 实现后输出完整解题过程",
        }

    async def run(self, state: dict) -> dict:
        """执行完整工作流"""
        return await self.graph.ainvoke(state)
