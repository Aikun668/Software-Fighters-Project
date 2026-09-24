"""追问澄清域路由：`/inquiry/resolve`、`/inquiry/resolve/plan`。"""

import asyncio
import json
import logging

from fastapi import APIRouter

import internal_api as api
from app.api.models import InquiryResolveRequest
from app.events.types import done_event, error_content_event
from app.utils.prompt_guard import sanitize_model
from internal_api._helpers import _sse_stream_chunks

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/inquiry/resolve")
async def inquiry_resolve(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后委派给 ResourceCenter 生成资源。"""
    body = sanitize_model(body)
    student_profile = body.student_profile

    inquiry = api._get_inquiry_service()
    resolved = inquiry.resolve(
        body.original_message,
        body.answers,
        questions=body.questions or None,
        suggested_types=body.suggested_types or None,
        clarified_topic=body.clarified_topic or None,
    )

    topic = resolved.get("topic", body.original_message)
    context_note = resolved.get("context_note", "")
    suggested_types = resolved.get("suggested_types", [])
    # 取第一个推荐类型作为 resource_type（单 Agent 路由）
    primary_type = suggested_types[0] if suggested_types else None

    logger.info(
        "Inquiry resolved: topic=%s, types=%s, primary=%s, answer_count=%d",
        topic, suggested_types, primary_type, len(body.answers),
    )

    enriched_profile = dict(student_profile)
    enriched_profile["_inquiry_context"] = context_note

    async def event_stream():
        async for event in api._get_resource_center().stream_generate(
            user_id=body.user_id,
            topic=topic,
            student_profile=enriched_profile,
            resource_type=primary_type or "",
        ):
            yield event.to_sse()

    return api.sse_response(event_stream())


@router.post("/inquiry/resolve/plan")
async def inquiry_resolve_plan(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后调用 LearningPathWorkflow 生成学习路径。"""
    body = sanitize_model(body)
    student_profile = body.student_profile

    inquiry = api._get_inquiry_service()
    resolved = inquiry.resolve(
        body.original_message,
        body.answers,
        questions=body.questions or None,
        suggested_types=body.suggested_types or None,
        clarified_topic=body.clarified_topic or None,
    )

    topic = resolved.get("topic", body.original_message)
    context_note = resolved.get("context_note", "")

    enriched_profile = dict(student_profile)
    enriched_profile["_inquiry_context"] = context_note

    path_workflow = api._get_path_workflow()

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'path', 'content': f'正在为「{topic}」规划学习路径...'}, ensure_ascii=False)}\n\n"

            path_state = await path_workflow.run({
                "user_id": body.user_id,
                "student_profile": enriched_profile,
                "topic": topic,
            })

            steps = path_state.get("steps", [])
            concept_graph = path_state.get("concept_graph", {})
            path_summary = path_state.get("response", "")

            yield f"data: {json.dumps({'type': 'path', 'steps': steps}, ensure_ascii=False)}\n\n"

            if path_summary:
                for chunk in _sse_stream_chunks(path_summary):
                    await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            done_payload: dict = {
                "type": "done",
                "mode": "research",
                "plan": {
                    "title": f"{topic}学习计划",
                    "topic": topic,
                    "total_steps": len(steps),
                    "steps": steps,
                    "concept_graph": concept_graph,
                }
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Inquiry resolve plan error: {e}", exc_info=True)
            # 同上：错误帧统一走事件工厂，不得换用 error_event（会多出 message 键）。
            yield error_content_event("学习路径生成失败，请稍后重试").to_sse()
            yield done_event().to_sse()

    return api.sse_response(event_stream())
