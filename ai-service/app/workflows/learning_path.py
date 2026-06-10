"""
LearningPathWorkflow — 学习路径规划 + 资源匹配编排工作流

借鉴 DeepTutor 顺序管道 + 修复子循环：
  Stage 1: 画像读取 → PathAgent.draft → steps + concept_graph
  Stage 2: PathAgent.revise → 审查修正（借鉴 DeepTutor repair sub-loop）
  Stage 3: 资源匹配 → 为每个 step 调 ContentAgent 生成匹配资源

Architecture #2: 纯 AI 生成。不再持久化（Java 从响应中提取结果后自行保存）。
"""

import asyncio
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.path_agent import PathAgent
from app.agents.content_agent import ContentAgent
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)


class LearningPathState(TypedDict, total=False):
    user_id: int
    student_profile: dict
    topic: str
    concept_graph: dict
    steps: list[dict]
    version: int
    resource_ids: list[int]
    response: str
    error: str


class LearningPathWorkflow(BaseWorkflow):
    """学习路径编排工作流 — 编排 PathAgent + ContentAgent"""

    def __init__(self, use_mock: bool = False):
        super().__init__(use_mock=use_mock)
        self.path_agent = PathAgent(use_mock_llm=use_mock)
        self.content_agent = ContentAgent(use_mock_llm=use_mock)

    def _build_graph(self):
        graph = StateGraph(LearningPathState)

        graph.add_node("draft", self._draft_node)
        graph.add_node("revise", self._revise_node)
        graph.add_node("match_resources", self._match_resources_node)
        graph.add_node("finalize", self._finalize_node)

        graph.set_entry_point("draft")
        graph.add_edge("draft", "revise")
        graph.add_edge("revise", "match_resources")
        graph.add_edge("match_resources", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    async def _draft_node(self, state: LearningPathState) -> dict:
        """Stage 1: 委托 PathAgent 设计初始路径"""
        student_profile = state.get("student_profile", {})
        topic = state.get("topic", "")

        path_state = {
            "student_profile": student_profile,
            "topic": topic,
        }
        result = await self.path_agent._draft_node(path_state)

        logger.info(f"Path draft generated: {len(result.get('steps', []))} steps")
        return result

    async def _revise_node(self, state: LearningPathState) -> dict:
        """Stage 2: 委托 PathAgent 审查修正（借鉴 DeepTutor repair sub-loop）"""
        student_profile = state.get("student_profile", {})
        steps = state.get("steps", [])
        concept_graph = state.get("concept_graph", {})
        topic = state.get("topic", "")

        path_state = {
            "steps": steps,
            "student_profile": student_profile,
            "concept_graph": concept_graph,
            "topic": topic,
        }
        result = await self.path_agent._revise_node(path_state)

        logger.info(f"Path revised: {len(result.get('steps', []))} steps (v{result.get('version', 2)})")
        return result

    async def _match_resources_node(self, state: LearningPathState) -> dict:
        """Stage 3: 为每个路径步骤并行生成资源预览"""
        steps = state.get("steps", [])
        student_profile = state.get("student_profile", {})

        async def _plan_one(step: dict) -> dict:
            topic = step.get("topic", "")
            if not topic:
                return step
            try:
                content_state = {"topic": topic, "student_profile": student_profile}
                result = await self.content_agent._plan_node(content_state)
                outline = result.get("outline", {})
                intro = outline.get("intro", f"{topic}的核心知识点")
                return {**step, "resource_id": None, "preview": intro[:120]}
            except Exception as e:
                logger.warning(f"Resource matching failed for step '{topic}': {e}")
                return {**step, "resource_id": None, "preview": "", "match_error": str(e)}

        tasks = [_plan_one(step) for step in steps]
        matched_steps = list(await asyncio.gather(*tasks))
        return {"steps": matched_steps}

    async def _finalize_node(self, state: LearningPathState) -> dict:
        """Stage 4: 聚合结果（不持久化，Java 从响应中提取）"""
        steps = state.get("steps", [])

        response = f"已为您规划 {len(steps)} 步学习路径，并匹配了对应资源。"
        return {
            "steps": steps,
            "resource_ids": [],
            "response": response,
            "concept_graph": state.get("concept_graph", {}),
            "version": state.get("version", 1),
        }
