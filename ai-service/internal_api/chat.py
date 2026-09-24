"""聊天域路由：`/api/chat`（统一入口）+ `/conversations/{id}/summary`。"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import SummaryRequest, UnifiedChatRequest
from app.utils.prompt_guard import sanitize_model

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/api/chat")
async def unified_chat(body: UnifiedChatRequest):
    return await _unified_chat(body)


async def _unified_chat(body: UnifiedChatRequest):
    """统一聊天路由：只做协议适配，业务编排全部在 ChatCenter.stream_chat()。

    职责（Task 3 收口）：
    1. sanitize_model + 基础输入处理；
    2. 调用 _get_chat_center().stream_chat(...)；
    3. 将 StreamEvent 转成 SSE 文本；
    4. 返回 sse_response(...)（媒体类型与心跳包装由该工厂负责）。

    正文聚合、推荐抽取、多 done 收敛、缺 done 兜底、错误补发等
    聊天级终态策略已移入 ChatCenter.stream_chat()，API 不再重复实现。
    """
    body = sanitize_model(body)
    message = body.message.strip()

    chat_center = api._get_chat_center()
    gen = chat_center.stream_chat(
        message=message,
        history=body.messages,
        mode=body.mode,
        student_profile=body.student_profile,
        user_id=body.user_id,
        conversation_id=body.conversation_id,
        style=body.style or "standard",
    )

    # 预取第一个事件：route 阶段异常在 HTTP 响应发送前暴露为 500，
    # 避免流已经发出 200 后内部再爆炸。
    try:
        first_event = await gen.__anext__()
    except Exception as e:
        logger.error(f"Chat pipeline failed before first event: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试", status_code=500)

    async def event_stream():
        yield first_event.to_sse()
        async for event in gen:
            yield event.to_sse()

    return api.sse_response(event_stream())


@router.post("/conversations/{conversation_id}/summary")
async def get_conversation_summary(conversation_id: int, body: SummaryRequest):
    """获取学习总结卡片。Java 传入原始消息列表，Python 用 LLM 生成总结。"""
    try:
        from app.utils.conversation_compress import format_messages_for_compress, llm_summarize

        messages_text = format_messages_for_compress(body.messages)
        summary = await llm_summarize("", messages_text)

        return api.api_success({
            "conversation_id": conversation_id,
            "summary": summary or "本次对话涵盖了多个学习主题。",
        })
    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "生成总结卡片失败", status_code=500)
