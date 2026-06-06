"""
ProfileWorkflow — 画像构建编排工作流

借鉴 OpenMAIC Director 图循环（START → extract → merge → director → response/complete）：
  extract:   LLM 从对话中抽取画像片段
  merge:     纯逻辑增量合并 + DB 持久化
  director:  纯逻辑判断——6 维度中 ≥4 个有值判定「完整」
             完整 → complete（触发下游通知）
             不完整 → response（生成追问，等待下一轮用户输入）

Director 节点是纯逻辑，不调用 LLM（借鉴 OpenMAIC director 纯代码路由策略）。
"""

import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.profile_agent import ProfileAgent, DIMENSIONS
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)

MIN_FILLED_DIMENSIONS = 4


class ProfileWorkflowState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    current_profile: dict
    extracted_fragment: dict
    profile_changed: bool
    profile_complete: bool
    filled_dimensions: int
    response: str
    last_extracted_msg_index: int


class ProfileWorkflow(BaseWorkflow):
    """画像构建编排工作流 — 包装 ProfileAgent + 完整度检测 + 下游通知"""

    def __init__(self, use_mock: bool = False):
        super().__init__(use_mock=use_mock)
        self.profile_agent = ProfileAgent(use_mock_llm=use_mock)

    def _build_graph(self):
        graph = StateGraph(ProfileWorkflowState)

        graph.add_node("extract", self._extract_node)
        graph.add_node("merge", self._merge_node)
        graph.add_node("director", self._director_node)
        graph.add_node("response", self._response_node)
        graph.add_node("complete", self._complete_node)

        graph.set_entry_point("extract")
        graph.add_edge("extract", "merge")
        graph.add_edge("merge", "director")

        graph.add_conditional_edges(
            "director",
            self._route_after_director,
            {
                "response": "response",
                "complete": "complete",
            },
        )

        graph.add_edge("response", END)
        graph.add_edge("complete", END)

        return graph.compile()

    async def _extract_node(self, state: ProfileWorkflowState) -> dict:
        """委托 ProfileAgent 的 extract 节点"""
        result = await self.profile_agent._extract_node(state)
        return result

    async def _merge_node(self, state: ProfileWorkflowState) -> dict:
        """委托 ProfileAgent 的 merge 节点（含 DB 持久化）"""
        result = await self.profile_agent._merge_node(state)
        return result

    async def _director_node(self, state: ProfileWorkflowState) -> dict:
        """纯逻辑：检查画像完整度（借鉴 OpenMAIC director 纯代码路由策略）"""
        current_profile = state.get("current_profile", {})
        status = self.check_profile_status(current_profile)

        logger.info(
            f"Profile director check: {status['filled_dimensions']}/{status['total_dimensions']} "
            f"dimensions filled, complete={status['complete']}"
        )
        return {
            "filled_dimensions": status["filled_dimensions"],
            "profile_complete": status["complete"],
        }

    async def _response_node(self, state: ProfileWorkflowState) -> dict:
        """委托 ProfileAgent 的 response 节点生成追问"""
        result = await self.profile_agent._response_node(state)
        return result

    async def _complete_node(self, state: ProfileWorkflowState) -> dict:
        """画像完整时：生成总结回复 + 触发下游通知"""
        filled = state.get("filled_dimensions", 0)

        response = (
            f"太棒了！我已经对你的学习情况有了比较全面的了解 "
            f"（已收集 {filled}/{len(DIMENSIONS)} 个维度）。"
            f"接下来我可以为你：\n"
            f"1. 生成个性化的学习资源\n"
            f"2. 规划适合你的学习路径\n"
            f"3. 推荐针对性的练习题\n"
            f"你想从哪里开始？"
        )

        logger.info(f"Profile completed for user {state.get('user_id')}: {filled} dimensions")
        return {"response": response, "profile_complete": True}

    @staticmethod
    def _route_after_director(state: ProfileWorkflowState) -> str:
        if state.get("profile_complete", False):
            return "complete"
        return "response"

    @staticmethod
    def check_profile_status(profile: dict) -> dict:
        """静态工具方法：检查画像完整度（供 API 端点直接调用）"""
        filled = sum(
            1 for k, v in profile.items()
            if v is not None and v != [] and k in DIMENSIONS
        )
        return {
            "complete": filled >= MIN_FILLED_DIMENSIONS,
            "filled_dimensions": filled,
            "total_dimensions": len(DIMENSIONS),
            "dimensions": list(DIMENSIONS),
        }
