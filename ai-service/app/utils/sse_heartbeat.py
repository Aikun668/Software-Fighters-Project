"""SSE 心跳保活包装器

借鉴 OpenMAIC app/api/chat/route.ts — :heartbeat 每 15s 发送一次 SSE 注释，
防止代理/浏览器在长时静默期间关闭连接。

SSE 注释格式: 以 ':' 开头的行被客户端忽略，但会计入连接活跃度。
"""

import asyncio
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

HEARTBEAT_MSG = ":heartbeat\n\n"
DEFAULT_INTERVAL = 15.0


async def sse_heartbeat_generator(
    event_generator: AsyncIterator[str],
    interval_sec: float = DEFAULT_INTERVAL,
) -> AsyncIterator[str]:
    """包裹 SSE 异步生成器，在空闲时注入心跳注释。

    子生成器产生的每一项都直接透传。当超过 interval_sec 秒没有新数据时，
    产生一个 ':heartbeat\\n\\n' SSE 注释行来保活连接。

    Args:
        event_generator: 原始的 SSE 事件异步生成器
        interval_sec: 心跳间隔（秒），默认 15

    Yields:
        SSE 事件字符串，与子生成器输出交织心跳注释
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=128)
    SENTINEL = object()
    _sentinel_sent = False

    async def _feed() -> None:
        nonlocal _sentinel_sent
        try:
            async for item in event_generator:
                await queue.put(item)
        except Exception:
            await queue.put(SENTINEL)
            _sentinel_sent = True
            raise
        finally:
            if not _sentinel_sent:
                await queue.put(SENTINEL)

    feeder = asyncio.ensure_future(_feed())

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
            yield item
    finally:
        feeder.cancel()
        try:
            await feeder
        except asyncio.CancelledError:
            pass
