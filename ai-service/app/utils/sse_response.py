"""SSE 响应工厂

`sse_heartbeat.py` 只负责纯生成器（不依赖 web 框架），本模块负责把生成器
组装成 HTTP 响应：媒体类型、心跳包装、StreamingResponse 样板。

抽取前这段样板在 `internal_api.py` 里逐字重复了 8 次。
"""

from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from app.utils.sse_heartbeat import DEFAULT_INTERVAL, sse_heartbeat_generator

SSE_MEDIA_TYPE = "text/event-stream"


def sse_response(
    event_generator: AsyncIterator[str],
    interval_sec: float = DEFAULT_INTERVAL,
) -> StreamingResponse:
    """把 SSE 事件生成器包成带心跳保活的流式响应。

    Args:
        event_generator: 产 SSE 文本的应用层生成器；心跳与边界终止由包装器负责
        interval_sec: 心跳间隔（秒），默认与 `sse_heartbeat` 一致

    Returns:
        media_type 为 text/event-stream 的 StreamingResponse
    """
    return StreamingResponse(
        sse_heartbeat_generator(event_generator, interval_sec=interval_sec),
        media_type=SSE_MEDIA_TYPE,
    )


def sse_sanitize(text: str) -> str:
    """移除用户文本中的 SSE 控制序列，防止伪造帧注入。

    ⚠️ 本轮仅从 `internal_api._sse_sanitize` 原样搬到此处归位，**没有任何调用点**。
    当前的防注入逻辑仍未生效，这不是一次修复。接线方式（在哪一层清洗、清洗
    哪些字段）需要先补「恶意换行 / 伪造 SSE 帧」契约测试再决定，与本次
    「零行为变化」的公共设施抽取分开处理。
    """
    return text.replace("\n\n", "  ").replace("\ndata:", " data:").replace("\r", "")
