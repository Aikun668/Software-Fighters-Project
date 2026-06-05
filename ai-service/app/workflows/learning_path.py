"""
LearningPathWorkflow — 学习路径规划 + 资源匹配编排工作流

借鉴 DeepTutor 顺序管道 + 修复子循环：
  Stage 1: 画像读取 → PathAgent.draft → steps + concept_graph
  Stage 2: PathAgent.revise → 审查修正（借鉴 DeepTutor repair sub-loop）
  Stage 3: 资源匹配 → 为每个 step 调 ContentAgent 生成匹配资源
           → resource_id 回填到 steps
           → 持久化 Resource + LearningRecord
"""

import asyncio
import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.path_agent import PathAgent
from app.agents.content_agent import ContentAgent
from app.db.database import get_db
from app.models.resource import Resource
from app.models.learning_record import LearningRecord
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)


class LearningPathState(TypedDict, total=False):
    user_id: int
    student_profile: dict
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
        graph.add_node("persist", self._persist_node)

        graph.set_entry_point("draft")
        graph.add_edge("draft", "revise")
        graph.add_edge("revise", "match_resources")
        graph.add_edge("match_resources", "persist")
        graph.add_edge("persist", END)

        return graph.compile()

    async def _draft_node(self, state: LearningPathState) -> dict:
        """Stage 1: 委托 PathAgent 设计初始路径"""
        student_profile = state.get("student_profile", {})

        path_state = {
            "student_profile": student_profile,
        }
        result = await self.path_agent._draft_node(path_state)

        logger.info(f"Path draft generated: {len(result.get('steps', []))} steps")
        return result

    async def _revise_node(self, state: LearningPathState) -> dict:
        """Stage 2: 委托 PathAgent 审查修正（借鉴 DeepTutor repair sub-loop）"""
        student_profile = state.get("student_profile", {})
        steps = state.get("steps", [])
        concept_graph = state.get("concept_graph", {})

        path_state = {
            "steps": steps,
            "student_profile": student_profile,
            "concept_graph": concept_graph,
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

    async def _persist_node(self, state: LearningPathState) -> dict:
        """Stage 4: 持久化路径步骤 + 对应资源到 DB"""
        user_id = state.get("user_id", 1)
        steps = state.get("steps", [])
        resource_ids = []

        try:
            async with get_db() as session:
                for idx, step in enumerate(steps):
                    topic = step.get("topic", "")
                    preview = step.get("preview", "")

                    resource = Resource(
                        user_id=user_id,
                        type="path_step",
                        topic=topic,
                        title=topic,
                        content_json={
                            "order": step.get("order", 0),
                            "status": step.get("status", "pending"),
                            "preview": preview,
                        },
                    )
                    session.add(resource)
                    await session.flush()

                    record = LearningRecord(
                        user_id=user_id,
                        resource_id=resource.id,
                        progress=0.0,
                    )
                    session.add(record)
                    resource_ids.append(resource.id)

                    # 回填 resource_id（不可变模式）
                    step = {**step, "resource_id": resource.id}
                    steps[idx] = step

                await session.commit()
                logger.info(f"Persisted path with {len(resource_ids)} steps for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to persist learning path: {e}")
            return {
                "steps": steps,
                "resource_ids": [],
                "error": f"持久化失败: {e}",
                "response": "路径规划成功，但保存失败，请稍后重试。",
                "concept_graph": state.get("concept_graph", {}),
                "version": state.get("version", 1),
            }

        response = f"已为您规划 {len(steps)} 步学习路径，并匹配了对应资源。"
        return {
            "steps": steps,
            "resource_ids": resource_ids,
            "response": response,
            "concept_graph": state.get("concept_graph", {}),
            "version": state.get("version", 1),
        }
