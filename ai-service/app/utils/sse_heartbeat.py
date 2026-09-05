"""SSE 心跳保活包装器

借鉴 OpenMAIC app/api/chat/route.ts — :heartbeat 每 15s 发送一次 SSE 注释，
防止代理/浏览器在长时静默期间关闭连接。

SSE 注释格式: 以 ':' 开头的行被客户端忽略，但会计入连接活跃度。
"""

import asyncio
import json
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

HEARTBEAT_MSG = ":heartbeat\n\n"
DEFAULT_INTERVAL = 15.0

# 边界终止责任：内部流异常/未终止时补发的兜底事件
_BOUNDARY_ERROR_MSG = 'data: {"type": "error", "content": "处理中断，请重试"}\n\n'
_BOUNDARY_DONE_MSG = 'data: {"type": "done"}\n\n'


def _sse_event_type(sse_str: str) -> str | None:
    """从单条 SSE 消息中解析业务 type；解析失败返回 None。"""
    for line in sse_str.split("\n"):
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip()).get("type")
            except (json.JSONDecodeError, AttributeError):
                return None
    return None


async def sse_heartbeat_generator(
    event_generator: AsyncIterator[str],
    interval_sec: float = DEFAULT_INTERVAL,
) -> AsyncIterator[str]:
    """包裹 SSE 异步生成器，在空闲时注入心跳注释。

    子生成器产生的每一项都直接透传。当超过 interval_sec 秒没有新数据时，
    产生一个 ':heartbeat\\n\\n' SSE 注释行来保活连接。

    终止责任：本包装器是流边界。内部生成器异常或正常结束但未发出 done 时，
    在此处补发唯一的终止事件（内部异常先补 error）；内部已发 done 则不重复。

    Args:
        event_generator: 原始的 SSE 事件异步生成器
        interval_sec: 心跳间隔（秒），默认 15

    Yields:
        SSE 事件字符串，与子生成器输出交织心跳注释
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=128)
    SENTINEL = object()
    inner_error = False

    async def _feed() -> None:
        nonlocal inner_error
        try:
            async for item in event_generator:
                await queue.put(item)
        except asyncio.CancelledError:
            raise
        except Exception:
            inner_error = True
            await queue.put(SENTINEL)
        finally:
            await queue.put(SENTINEL)

    feeder = asyncio.ensure_future(_feed())
    saw_done = False

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    queue.get(), timeout=interval_sec
                )
            except asyncio.TimeoutError:
                yield HEARTBEAT_MSG
                continue

            if item is SENTINEL:
                break
            if _sse_event_type(item) == "done":
                saw_done = True
            yield item

        # 边界兜底：保证客户端总能收到唯一终止事件
        if not saw_done:
            if inner_error:
                yield _BOUNDARY_ERROR_MSG
            yield _BOUNDARY_DONE_MSG
    finally:
        feeder.cancel()
        try:
            await feeder
        except (asyncio.CancelledError, Exception):
            pass
