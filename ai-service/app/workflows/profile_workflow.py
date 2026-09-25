"""
ProfileWorkflow — 画像构建编排工作流（**单层图**，P3-B3b 合并）

结构（合并后）：
  pipeline:            **委托 `ProfileAgent.run()`** —— 唯一画像管线
                       （extract → semantic_judge → merge → audit → respond）
  completeness_check:  纯逻辑判断——6 维度中 ≥4 个有值判定「完整」
                       完整 → complete（触发下游通知）
                       不完整 → 结束（`respond` 已在 pipeline 内产出追问）

**为什么合并（P3-B3b）**：合并前是两层图 —— 外层 5 节点（extract/merge/
completeness_check/response/complete）逐节点转发内层同名节点，**内层的
`semantic_judge`（语义去重）与 `audit`（画像审计）在生产路径从未执行**：
设计好的画像质量能力被静默跳过。合并后只有一层，管线即 `ProfileAgent` 的图。

**行为变更（本轮已验收）**：

| 变化 | 说明 |
|---|---|
| `semantic_judge` 开始执行 | merge 前用 Flash 模型做语义去重；embedding 预筛 `DEDUP_PREFILTER=0.45`，**无候选不调 LLM**；异常回退 embedding |
| `audit` 开始执行 | 每 `AUDIT_MSG_INTERVAL=20` 条抽取消息一次；无 weak_points/interest 条目时直接返回 |
| `respond` 由「仅不完整分支」变为「管线末节点」 | 完整分支下其输出会被 `complete` 的固定文案覆盖，**用户可见输出不变**，代价是完成那一轮多一次 LLM 调用 |
| `_postprocess_output` 安全扫描 | 走 `BaseAgent.run` 后，画像路径也过一遍出站安全检查（防御纵深） |

**回退**：把 `_build_graph` 的 `pipeline` 节点换回原 5 节点转发版即可（原实现见
`验收记录/P3-B3b-单层化-2026-09-25.md` §回退）。

【命名澄清】本工作流的 `completeness_check` **图节点**（`_completeness_check_node`）
  是纯算术完整度判断（6 维中 ≥4 个有值 → 完整）。
  ⚠️ 该节点原名 `director`，与 `app/orchestration/resource_selector.py` 的
  `ResourceAgentSelector`（资源 Agent 选择器）、`llm_service.PROFILE_DIRECTOR`（模型常量）
  **同名不同责**；P3-B1 已改名（见 `验收记录/P3-B1-结构收敛-*.md`）。
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

        graph.add_node("pipeline", self._pipeline_node)
        graph.add_node("completeness_check", self._completeness_check_node)
        graph.add_node("complete", self._complete_node)

        graph.set_entry_point("pipeline")
        graph.add_edge("pipeline", "completeness_check")

        # 路由字符串保持 `response` / `complete`（`_route_after_completeness_check`
        # 的既有语义与测试不变）；`response` 已在 pipeline 内产出，故映射到图终点。
        graph.add_conditional_edges(
            "completeness_check",
            self._route_after_completeness_check,
            {
                "response": END,
                "complete": "complete",
            },
        )

        graph.add_edge("complete", END)

        return graph.compile()

    async def _pipeline_node(self, state: ProfileWorkflowState) -> dict:
        """委托 `ProfileAgent.run()` —— 单层化的唯一入口。

        走 `run()` 而非逐节点转发，是为了让 `semantic_judge` / `audit`
        真正进入生产路径（合并前它们被外层图绕过，从未执行）。
        """
        return await self.profile_agent.run(state)

    async def _completeness_check_node(self, state: ProfileWorkflowState) -> dict:
        """纯逻辑：检查画像完整度（纯算术判定，不调用 LLM）"""
        current_profile = state.get("current_profile", {})
        status = self.check_profile_status(current_profile)

        logger.info(
            f"Profile completeness check: {status['filled_dimensions']}/{status['total_dimensions']} "
            f"dimensions filled, complete={status['complete']}"
        )
        return {
            "filled_dimensions": status["filled_dimensions"],
            "profile_complete": status["complete"],
        }

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
    def _route_after_completeness_check(state: ProfileWorkflowState) -> str:
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
