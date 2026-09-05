import asyncio
import logging
from typing import Any, AsyncGenerator

from app.agents.adjustment_agent import AdjustmentAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.goal_agent import GoalAgent
from app.agents.layered_explain_agent import LayeredExplainAgent
from app.agents.schedule_agent import ScheduleAgent
from app.centers.auto_center import AutoCenter
from app.centers.exercise_center import ExerciseCenter
from app.centers.plan_center import PlanCenter
from app.centers.resource_center import ResourceCenter
from app.centers.schemas import (
    AggregatedResult,
    CenterResult,
    CenterTask,
    ExecutionPlan,
)
from app.centers.visualization_center import VisualizationCenter
from app.events.types import (
    StreamEvent,
    StreamEventType,
    center_end_event,
    center_start_event,
    done_event,
    error_event,
    inquiry_event,
    knowledge_candidates_event,
)
from app.services.graph_service import get_graph_service
from app.services.knowledge_extraction import extract_knowledge_nodes

logger = logging.getLogger(__name__)


class ResultAgent:
    CENTER_DELAY_SECONDS = 0.0

    _KG_EXTRACTION_SKIP_INTENTS: frozenset[str] = frozenset(
        {"profile_building", "exercise_gen", "solve_problem", "inquiry", "unknown"}
    )

    def __init__(
        self,
        auto_center: AutoCenter | None = None,
        plan_center: PlanCenter | None = None,
        resource_center: ResourceCenter | None = None,
        exercise_center: ExerciseCenter | None = None,
        visualization_center: VisualizationCenter | None = None,
        decompose_agent: DecomposeAgent | None = None,
        layered_explain_agent: LayeredExplainAgent | None = None,
        goal_agent: GoalAgent | None = None,
        schedule_agent: ScheduleAgent | None = None,
        adjustment_agent: AdjustmentAgent | None = None,
    ):
        # AutoCenter 的各 Agent 由其内部惰性默认构造；
        # decompose/layered_explain 仅 PlanCenter/AutoCenter 显式注入时使用
        self.auto_center = auto_center or AutoCenter()
        self.plan_center = plan_center or PlanCenter(
            goal_agent=goal_agent,
            decompose_agent=decompose_agent,
            schedule_agent=schedule_agent,
            adjustment_agent=adjustment_agent,
        )
        self.resource_center = resource_center or ResourceCenter()
        self.exercise_center = exercise_center or ExerciseCenter()
        self.visualization_center = visualization_center or VisualizationCenter()

    async def execute(
        self,
        plan: ExecutionPlan,
        event_queue: asyncio.Queue | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        if plan.tasks and plan.tasks[0].mode == "inquiry":
            task = plan.tasks[0]
            question = task.params.get("question", "你想了解什么？")
            yield inquiry_event(question)
            yield done_event({
                "type": "inquiry",
                "question": question,
                "is_clear": False,
            })
            return

        aggregated = AggregatedResult()
        total = len(plan.tasks)

        for idx, task in enumerate(plan.tasks):
            progress = round((idx / total) * 100) / 100 if total else 0.0
            yield center_start_event(
                center=task.mode,
                message=f"开始执行 {task.mode} 中心...",
                sequence=idx,
            )

            result = await self._execute_task(task)
            aggregated.results.append(result)

            yield center_end_event(
                center=task.mode,
                message=f"{task.mode} 中心执行完成",
                sequence=idx,
            )

            yield self._result_to_event(result, progress)

            if result.profile_delta:
                aggregated.profile_delta.update(result.profile_delta)

            if self.CENTER_DELAY_SECONDS > 0 and idx < total - 1:
                await asyncio.sleep(self.CENTER_DELAY_SECONDS)

        summary = self._build_summary(aggregated)
        aggregated.summary = summary
        aggregated.next_steps = self._build_next_steps(aggregated)

        kg_event = await self._maybe_emit_knowledge_candidates(plan, aggregated)
        if kg_event is not None:
            yield kg_event

        yield done_event({
            "type": "done",
            "summary": summary,
            "next_steps": aggregated.next_steps,
            "profile_delta": aggregated.profile_delta,
            "results": [self._serialize_result(r) for r in aggregated.results],
        })

    async def _execute_task(self, task: CenterTask) -> CenterResult:
        try:
            if task.mode == "auto":
                return await self.auto_center.execute(task)
            if task.mode == "plan":
                return await self.plan_center.execute(task)
            if task.mode == "resource":
                return await self.resource_center.execute(task)
            if task.mode == "exercise":
                return await self.exercise_center.execute(task)
            if task.mode == "visualization":
                return await self.visualization_center.execute(task)
            return CenterResult(
                mode=task.mode,
                intent=task.intent,
                event_type="error",
                error=f"未知 center: {task.mode}",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"ResultAgent execute task failed: {e}")
            return CenterResult(
                mode=task.mode,
                intent=task.intent,
                event_type="error",
                error="处理失败",
                sequence=task.sequence,
            )

    def _result_to_event(self, result: CenterResult, progress: float) -> StreamEvent:
        if result.error:
            return error_event(
                stage=result.mode,
                message=result.error,
            )
        return StreamEvent(
            type=self._map_event_type(result.event_type),
            stage=result.mode,
            message=f"{result.agent} 输出",
            progress=progress,
            data=result.payload,
        )

    def _map_event_type(self, event_type: str) -> StreamEventType:
        mapping = {
            "content": StreamEventType.CONTENT,
            "plan": StreamEventType.CONTENT,
            "resource": StreamEventType.CONTENT,
            "exercise": StreamEventType.CONTENT,
            "visualization": StreamEventType.CONTENT,
            "error": StreamEventType.ERROR,
            "inquiry": StreamEventType.INQUIRY,
        }
        return mapping.get(event_type, StreamEventType.CONTENT)

    def _build_summary(self, aggregated: AggregatedResult) -> str:
        if not aggregated.results:
            return "已完成处理。"
        parts = []
        for r in aggregated.results:
            if r.error:
                parts.append(f"{r.mode} 执行出现错误")
            else:
                parts.append(f"{r.mode} 已完成")
        return "；".join(parts) + "。"

    def _build_next_steps(self, aggregated: AggregatedResult) -> list[str]:
        steps = []
        intents = [r.intent for r in aggregated.results if not r.error]
        if "learning_path" in intents and "exercise_gen" not in intents:
            steps.append("可以尝试生成配套练习题巩固路径内容")
        if "exercise_gen" in intents and "learning_path" not in intents:
            steps.append("可以规划系统学习路径")
        if "resource_gen" in intents:
            steps.append("可以导出为 PPT/PDF 便于复习")
        return steps

    def _serialize_result(self, result: CenterResult) -> dict[str, Any]:
        return {
            "mode": result.mode,
            "intent": result.intent,
            "event_type": result.event_type,
            "agent": result.agent,
            "sequence": result.sequence,
            "error": result.error,
            "payload_keys": list(result.payload.keys()),
        }

    async def _maybe_emit_knowledge_candidates(
        self,
        plan: ExecutionPlan,
        aggregated: AggregatedResult,
    ) -> StreamEvent | None:
        if not aggregated.results:
            return None

        eligible_results = [
            r for r in aggregated.results
            if not r.error and r.intent not in self._KG_EXTRACTION_SKIP_INTENTS
        ]
        if not eligible_results:
            return None

        user_message = plan.intent_meta.get("raw_message") or (
            plan.tasks[0].input if plan.tasks else ""
        )
        assistant_reply = self._build_assistant_reply(aggregated.results)
        if not user_message.strip() or not assistant_reply.strip():
            return None

        course_id: str = ""
        if plan.tasks:
            course_id = str(plan.tasks[0].context.get("course_id", ""))
        existing_node_ids = self._load_existing_node_ids()
        extract_task = asyncio.create_task(
            extract_knowledge_nodes(
                course_id=course_id,
                user_message=user_message,
                assistant_reply=assistant_reply,
                existing_node_ids=existing_node_ids,
            )
        )

        try:
            groups = await asyncio.wait_for(extract_task, timeout=15.0)
        except Exception as exc:
            logger.warning("Knowledge node extraction failed: %s", exc)
            return None

        if groups and any(groups.get(k) for k in ("primary", "related", "broad")):
            return knowledge_candidates_event(groups)
        return None

    def _build_assistant_reply(self, results: list[CenterResult]) -> str:
        parts = []
        for result in results:
            if result.error:
                continue
            text = self._extract_reply_text(result)
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    @staticmethod
    def _extract_reply_text(result: CenterResult) -> str:
        payload = result.payload or {}
        for key in ("response", "solution", "summary"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        blocks = payload.get("blocks") or payload.get("content_blocks") or []
        if isinstance(blocks, list):
            texts: list[str] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                for field in ("content", "text", "title", "heading"):
                    value = block.get(field)
                    if isinstance(value, str) and value.strip():
                        texts.append(value.strip())
            if texts:
                return "\n".join(texts)

        return ""

    @staticmethod
    def _load_existing_node_ids() -> set[str]:
        try:
            graph_service = get_graph_service()
            skeleton = graph_service.load_skeleton()
            return {
                str(node.get("id", "")).strip()
                for node in skeleton.get("nodes", [])
                if node.get("id")
            }
        except Exception as exc:
            logger.warning("Failed to load existing graph node ids: %s", exc)
            return set()
