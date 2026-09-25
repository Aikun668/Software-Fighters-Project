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
    """移除文本中的 SSE 控制序列（`\\n\\n` / `\\ndata:` / `\\r`）。

    ⚠️ **本函数不得接线** —— 这不是「还没接」，而是「接线是错的」。
    依据是 `tests/test_sse_forgery_contract.py`（P3-C 轮补的前置契约测试）：

    - **威胁已不存在**：本服务所有 SSE 帧的载荷都由 `json.dumps` 编码
      （`StreamEvent.to_sse()` 与各端点的 `f"data: {json.dumps(...)}"`），
      真实换行被转义成字面 `\\n`，内容里的换行**永远变不成帧分隔符**。
      `FG-A01/A02/A03` 用真实 ASGI 注入伪造 done 帧，证明帧数守恒、done 唯一、每帧单行。
    - **帧层接线会破坏协议**：帧结束符本身就是 `\\n\\n`，会被本函数吃掉（`FG-C01`）。
    - **内容层接线会损坏渲染**：markdown 段落空行 `\\n\\n` → 两个空格（`FG-C02`）。

    真正的防护是「帧载荷必须 JSON 编码」，由 `FG-B01/B02` 用 AST 锁死新写的帧；
    本函数保持**零调用**，由 `SSE-D17` / `ERR-B06` 两把锁跨轮守护。
    """
    return text.replace("\n\n", "  ").replace("\ndata:", " data:").replace("\r", "")
