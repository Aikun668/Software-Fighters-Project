"""画像域路由：`/profile/chat`、`/profile/workflow/status`。"""

import asyncio
import json
import logging

from fastapi import APIRouter

import internal_api as api
from app.api.models import ProfileChatRequest, ProfileWorkflowStatusRequest
from app.events.types import done_event, error_content_event
from app.utils.prompt_guard import sanitize_model
from internal_api._helpers import _sse_stream_chunks

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/profile/chat")
async def profile_chat(body: ProfileChatRequest):
    body = sanitize_model(body)
    messages = body.messages
    current_profile = body.student_profile

    workflow = api._get_profile_workflow()

    async def event_stream():
        try:
            state = await workflow.run({
                "messages": messages,
                "user_id": body.user_id,
                "current_profile": current_profile,
            })

            response = state.get("response", "")
            if response:
                for chunk in _sse_stream_chunks(response):
                    await asyncio.sleep(0.04)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            if state.get("profile_changed"):
                yield f"data: {json.dumps({'type': 'profile_update', 'content': state.get('current_profile', {})}, ensure_ascii=False)}\n\n"

            if state.get("profile_complete"):
                yield f"data: {json.dumps({'type': 'profile_complete', 'filled_dimensions': state.get('filled_dimensions', 0)}, ensure_ascii=False)}\n\n"

            done_payload = {"type": "done"}
            if state.get("profile_changed"):
                done_payload["profile_delta"] = state.get("current_profile", {})
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Profile chat SSE error: {e}", exc_info=True)
            # 错误帧统一走事件工厂。⚠️ 必须用 error_content_event，
            # 不能用 error_event(stage, message) —— 后者同时写 message 与 content 两个键，
            # 响应字节会变（实测见 tests/test_error_fallback_contract.py::ERR-A01）。
            yield error_content_event("画像对话失败，请稍后重试").to_sse()
            yield done_event().to_sse()

    return api.sse_response(event_stream())


@router.post("/profile/workflow/status")
async def profile_workflow_status(body: ProfileWorkflowStatusRequest):
    workflow = api._get_profile_workflow()
    status = workflow.check_profile_status(body.student_profile)
    return api.api_success(status)
