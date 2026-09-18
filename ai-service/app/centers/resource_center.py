import asyncio
import logging
from typing import Any, AsyncIterator, Optional

from app.centers.schemas import CenterResult, CenterTask
from app.events.types import StreamEventType, done_event
from app.services.inquiry_service import InquiryService
from app.workflows.resource_gen import ResourceGenWorkflow

logger = logging.getLogger(__name__)


class ResourceCenter:
    def __init__(self, resource_workflow=None, content_agent=None, inquiry_service=None):
        self.resource_workflow = resource_workflow
        self.content_agent = content_agent
        self.inquiry_service = inquiry_service

    async def execute(self, task: CenterTask, event_queue=None) -> CenterResult:
        """聊天路径：先 InquiryService.check，清晰后调 _run_generation。"""
        context = task.context or {}
        student_profile = context.get("student_profile", {})
        user_id = context.get("user_id", 1)
        topic = task.params.get("topic") or task.input

        try:
            inquiry = self.inquiry_service or InquiryService()
            check_result = await inquiry.check(task.input, student_profile)

            if not check_result.is_clear:
                return CenterResult(
                    mode="resource",
                    intent=task.intent,
                    event_type="inquiry",
                    payload={
                        "type": "inquiry",
                        "is_clear": False,
                        "clarified_topic": check_result.clarified_topic or topic,
                        "questions": check_result.questions,
                        "rationale": check_result.rationale,
                    },
                    agent="InquiryService",
                    sequence=task.sequence,
                )

            suggested_types = task.params.get("suggested_types", [])
            primary_type = suggested_types[0] if suggested_types else ""

            state = await self._run_generation(
                user_id=user_id,
                topic=check_result.clarified_topic or topic,
                student_profile=student_profile,
                resource_type=primary_type,
                event_queue=event_queue,
            )

            return CenterResult(
                mode="resource",
                intent=task.intent,
                event_type="resource",
                payload={
                    "type": "resource",
                    "content_blocks": state.get("content_blocks", []),
                    "questions": state.get("questions", []),
                    "response": state.get("response", ""),
                },
                agent=f"ResourceGenWorkflow/{state.get('agent_name', 'content')}",
                sequence=task.sequence,
            )
        except Exception as e:
            logger.error(f"ResourceCenter failed: {e}")
            return CenterResult(
                mode="resource",
                intent=task.intent,
                event_type="error",
                error="资源生成失败",
                agent="ResourceGenWorkflow/error",
                sequence=task.sequence,
            )

    async def _run_generation(
        self,
        *,
        user_id: int,
        topic: str,
        student_profile: dict,
        resource_type: str,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> dict:
        """资源域唯一允许调用 ResourceGenWorkflow.run() 的位置。

        每次请求仅运行一次 Workflow；event_queue 非空时透传给 Workflow（用于内部进度事件）。
        """
        workflow = self.resource_workflow or ResourceGenWorkflow()
        workflow_state: dict[str, Any] = {
            "user_id": user_id,
            "topic": topic,
            "student_profile": student_profile,
            "resource_type": resource_type or "",
        }
        if event_queue is not None:
            workflow_state["event_queue"] = event_queue
        return await workflow.run(workflow_state)

    @staticmethod
    def _done_payload(state: dict) -> dict:
        """构造 done_event.data 应当包含的完整终态 payload。"""
        return {
            "content_blocks": state.get("content_blocks", []),
            "questions": state.get("questions", []),
            "response": state.get("response", ""),
            "error": state.get("error", ""),
            "review_status": state.get("review_status", "not_applicable"),
            "repair_attempted": state.get("repair_attempted", False),
            "fallback_used": state.get("fallback_used", False),
            "final_status": state.get("final_status", "success"),
        }

    async def stream_generate(
        self,
        *,
        user_id: int,
        topic: str,
        student_profile: dict,
        resource_type: str,
    ) -> AsyncIterator[Any]:
        """业务事件流：调一次 _run_generation 并 yield StreamEvent，含恰好一个 done。

        - 后台 producer 调用 _run_generation(..., event_queue=queue) 一次
        - producer 成功时 yield done_event(_done_payload(state))
        - producer 异常时 yield done_event({"error": "资源生成失败，请稍后重试"})
        - consumer 持续 yield queue 中的事件，遇到 done 停止
        - 消费者取消时取消 producer，避免孤儿 Workflow
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)

        async def producer() -> None:
            try:
                state = await self._run_generation(
                    user_id=user_id,
                    topic=topic,
                    student_profile=student_profile,
                    resource_type=resource_type,
                    event_queue=queue,
                )
                await queue.put(done_event(self._done_payload(state)))
            except Exception as e:
                logger.error(f"ResourceCenter stream_generate failed: {e}", exc_info=True)
                await queue.put(done_event({"error": "资源生成失败，请稍后重试"}))

        producer_task = asyncio.create_task(producer())

        try:
            while True:
                event = await queue.get()
                yield event
                if event.type == StreamEventType.DONE:
                    break
        finally:
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, Exception):
                    pass
