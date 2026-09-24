"""答疑域路由：`/tutor/chat`。"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.models import TutorChatRequest
from app.utils.prompt_guard import sanitize_model

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/tutor/chat")
async def tutor_chat(body: TutorChatRequest):
    body = sanitize_model(body)
    messages = body.messages
    student_profile = body.student_profile

    async def event_stream():
        async for event in api._get_tutor_center().stream_chat(
            messages=messages,
            student_profile=student_profile,
        ):
            yield event.to_sse()

    return api.sse_response(event_stream())
