"""
ResourceGenWorkflow — 多 Agent 协同资源生成工作流

借鉴 OpenMAIC 两阶段生成管道（outline → parallel generate）：
  Stage 1: 大纲规划（ContentAgent._plan_node）
  Stage 2: 并行生成 5 类资源（asyncio.gather，借鉴 DeepTutor research pipeline）
  Stage 3: 持久化到 Resource 表

共享 outline 保证资源间一致性（借鉴 OpenMAIC 共享上下文模式）。
"""

import asyncio
import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.content_agent import ContentAgent
from app.agents.exercise_agent import ExerciseAgent
from app.db.database import get_db
from app.models.resource import Resource
from app.workflows.base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)

class ResourceGenState(TypedDict, total=False):
    user_id: int
    topic: str
    student_profile: dict
    outline: dict
    content_blocks: list[dict]
    questions: list[dict]
    resource_ids: list[int]
    response: str
    error: str


class ResourceGenWorkflow(BaseWorkflow):
    """资源生成工作流 — 编排 ContentAgent + ExerciseAgent 协同产出 5 类资源"""

    def __init__(self, use_mock: bool = False):
        super().__init__(use_mock=use_mock)
        self.content_agent = ContentAgent(use_mock_llm=use_mock)
        self.exercise_agent = ExerciseAgent(use_mock_llm=use_mock)

    def _build_graph(self):
        graph = StateGraph(ResourceGenState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("persist", self._persist_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "persist")
        graph.set_finish_point("persist")
        return graph.compile()

    async def _plan_node(self, state: ResourceGenState) -> dict:
        """Stage 1: 调用 ContentAgent 生成知识大纲"""
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})

        content_state = {
            "topic": topic,
            "student_profile": student_profile,
        }
        result = await self.content_agent._plan_node(content_state)
        outline = result.get("outline", {})

        logger.info(f"Outline generated for topic '{topic}': {len(outline.get('subsections', []))} subsections")
        return {"outline": outline}

    async def _generate_node(self, state: ResourceGenState) -> dict:
        """Stage 2: 并行生成 5 类资源（借鉴 DeepTutor asyncio.gather 并行模式）"""
        topic = state.get("topic", "")
        student_profile = state.get("student_profile", {})
        outline = state.get("outline", {})

        content_state = {
            "topic": topic,
            "student_profile": student_profile,
            "outline": outline,
        }
        exercise_state = {
            "topic": topic,
            "count": 5,
            "difficulty": "medium",
            "student_profile": student_profile,
        }

        # 3 路并行：课程内容 + 练习题 + 拓展阅读
        results = await asyncio.gather(
            self.content_agent._generate_node(content_state),
            self.exercise_agent.run(exercise_state),
            self._generate_extended_reading(topic, student_profile, outline),
            return_exceptions=True,
        )

        content_result, exercise_result, reading_result = results
        for label, r in zip(["content", "exercise", "reading"], results):
            if isinstance(r, BaseException):
                logger.error(f"{label} generation failed: {r}")

        content_blocks = content_result.get("content_blocks", []) if isinstance(content_result, dict) else []
        questions = exercise_result.get("questions", []) if isinstance(exercise_result, dict) else []
        reading_blocks = reading_result if isinstance(reading_result, list) else []

        all_blocks = content_blocks + reading_blocks

        logger.info(f"Generated {len(all_blocks)} content blocks + {len(questions)} questions for '{topic}'")
        return {
            "content_blocks": all_blocks,
            "questions": questions,
        }

    async def _generate_extended_reading(
        self, topic: str, student_profile: dict, outline: dict
    ) -> list[dict]:
        """生成拓展阅读块（application/comparison 类型）"""
        from app.utils.prompt_loader import interpolate_variables

        sys_prompt = self.content_agent._load_extra_prompt("deep_dive.yaml", key="system")
        user_tpl = self.content_agent._load_extra_prompt("deep_dive.yaml", key="user_template")
        profile_text = self.content_agent._format_profile(student_profile)

        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "topic_summary": f"{topic}的拓展应用",
                "objectives": f"了解{topic}的实际应用场景",
                "focus_topic": topic,
                "knowledge_context": "",
                "student_profile": profile_text,
            },
        )

        try:
            result = await self.content_agent._call_llm_json(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                expected_key="suggestions",
                fallback={},
            )
            suggestions = result.get("suggestions", [])
            if suggestions:
                lines = [f"**{topic} 拓展阅读**\n"]
                for s in suggestions:
                    lines.append(f"- **{s.get('topic', '')}**: {s.get('rationale', '')}")
                return [{"type": "callout", "heading": "拓展阅读", "content": "\n".join(lines)}]
        except Exception as e:
            logger.warning(f"Extended reading generation failed: {e}")

        return [{"type": "callout", "heading": "拓展阅读", "content": f"**{topic} 拓展阅读**\n\n更多相关内容正在整理中。"}]

    async def _persist_node(self, state: ResourceGenState) -> dict:
        """Stage 3: 持久化资源到 Resource 表"""
        user_id = state.get("user_id", 1)
        topic = state.get("topic", "")
        content_blocks = state.get("content_blocks", [])
        questions = state.get("questions", [])
        resource_ids = []

        try:
            async with get_db() as session:
                # 保存课程文档
                doc_resource = Resource(
                    user_id=user_id,
                    type="course_doc",
                    topic=topic,
                    title=f"{topic} 课程文档",
                    content_json={"blocks": content_blocks},
                )
                session.add(doc_resource)
                await session.flush()
                resource_ids.append(doc_resource.id)

                # 保存练习题
                if questions:
                    quiz_resource = Resource(
                        user_id=user_id,
                        type="exercises",
                        topic=topic,
                        title=f"{topic} 练习题",
                        content_json={"questions": questions},
                    )
                    session.add(quiz_resource)
                    await session.flush()
                    resource_ids.append(quiz_resource.id)

                # 保存思维导图（从 content_blocks 提取）
                mindmap_blocks = [b for b in content_blocks if b.get("type") == "mindmap"]
                if mindmap_blocks:
                    mm_resource = Resource(
                        user_id=user_id,
                        type="mindmap",
                        topic=topic,
                        title=f"{topic} 思维导图",
                        content_json={"mindmap": mindmap_blocks[0].get("content", "")},
                    )
                    session.add(mm_resource)
                    await session.flush()
                    resource_ids.append(mm_resource.id)

                await session.commit()
                logger.info(f"Persisted {len(resource_ids)} resources for user {user_id}, topic '{topic}'")
        except Exception as e:
            logger.error(f"Failed to persist resources: {e}")
            return {
                "resource_ids": [],
                "error": f"持久化失败: {e}",
                "response": "资源生成成功，但保存失败，请稍后重试。",
            }

        response = f"已为您生成「{topic}」的学习资源，共 {len(content_blocks)} 个内容块 + {len(questions)} 道练习题。"
        return {
            "resource_ids": resource_ids,
            "response": response,
        }
