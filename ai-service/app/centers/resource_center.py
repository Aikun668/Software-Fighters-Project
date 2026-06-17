import logging
from typing import Any

from app.centers.schemas import CenterResult, CenterTask
from app.services.inquiry_service import InquiryService
from app.workflows.resource_gen import ResourceGenWorkflow

logger = logging.getLogger(__name__)


class ResourceCenter:
    def __init__(self, resource_workflow=None, content_agent=None, inquiry_service=None):
        self.resource_workflow = resource_workflow
        self.content_agent = content_agent
        self.inquiry_service = inquiry_service

    async def execute(self, task: CenterTask, event_queue=None) -> CenterResult:
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

            workflow = self.resource_workflow or ResourceGenWorkflow()
            suggested_types = task.params.get("suggested_types", [])
            workflow_state = {
                "user_id": user_id,
                "topic": check_result.clarified_topic or topic,
                "student_profile": student_profile,
                "resource_type": suggested_types[0] if suggested_types else "",
            }
            if event_queue is not None:
                workflow_state["event_queue"] = event_queue
            state = await workflow.run(workflow_state)

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
