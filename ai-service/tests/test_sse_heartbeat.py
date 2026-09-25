"""Tests for SSE heartbeat keepalive wrapper.

P3-C 轮修订：本文件原先 5 例锁的是**旧设计**（逐项透传、子生成器异常向上抛、
空子生成器输出为空）。现行设计是「**包装器即流边界**」——内部异常或未发 done 时，
在此处补发唯一的终止事件（内部异常→error；未终结→done）。5 例已按现行设计重写，
不再是「陈旧红测试」。
"""
import asyncio

import pytest

from app.utils.sse_heartbeat import (
    DEFAULT_INTERVAL,
    HEARTBEAT_MSG,
    _BOUNDARY_DONE_MSG,
    _BOUNDARY_ERROR_MSG,
    sse_heartbeat_generator,
)


async def _real_sleep(seconds: float) -> None:
    """Sleep using loop.call_later, bypassing the global asyncio.sleep mock in conftest.py."""
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    loop.call_later(seconds, event.set)
    await event.wait()


async def _make_generator(items: list[str], delays: list[float] | None = None):
    """Helper: yield items, sleeping *before* each item.

    delays[i] = seconds to wait before yielding items[i].
    Uses _real_sleep to bypass the asyncio.sleep mock in conftest.py.
    """
    if delays is None:
        delays = [0.0] * len(items)
    for item, delay in zip(items, delays, strict=False):
        if delay > 0:
            await _real_sleep(delay)
        yield item


@pytest.mark.asyncio
async def test_yields_child_items():
    """子生成器已发 done → 逐项透传，且**不重复**补 done。"""
    items = ['data: {"type": "token", "content": "hello"}\n\n', _BOUNDARY_DONE_MSG]
    wrapped = sse_heartbeat_generator(_make_generator(items))
    result = [item async for item in wrapped]
    assert result == items


@pytest.mark.asyncio
async def test_yields_heartbeat_during_idle():
    """Child sleeps long enough that heartbeat fires between items."""
    items = ["first\n\n", "last\n\n"]
    wrapped = sse_heartbeat_generator(
        _make_generator(items, delays=[0.0, 1.0]),
        interval_sec=0.2,
    )
    result = [item async for item in wrapped]
    assert items[0] in result
    assert items[1] in result
    assert HEARTBEAT_MSG in result


@pytest.mark.asyncio
async def test_no_heartbeat_when_active():
    """子生成器够快 → 无心跳；但未发 done，故末尾补一个终止事件。"""
    items = [f"item{i}\n\n" for i in range(20)]
    wrapped = sse_heartbeat_generator(
        _make_generator(items, delays=[0.01] * 20),
        interval_sec=0.5,
    )
    result = [item async for item in wrapped]
    assert HEARTBEAT_MSG not in result
    assert result == [*items, _BOUNDARY_DONE_MSG]


@pytest.mark.asyncio
async def test_stops_with_child():
    """子生成器正常结束但未发 done → 边界补唯一 done。"""
    items = ["only\n\n"]
    wrapped = sse_heartbeat_generator(
        _make_generator(items), interval_sec=0.1
    )
    result = [item async for item in wrapped]
    assert result == [*items, _BOUNDARY_DONE_MSG]


@pytest.mark.asyncio
async def test_empty_child():
    """空子生成器也要给出终止事件（客户端不能空等）。"""
    wrapped = sse_heartbeat_generator(_make_generator([]), interval_sec=0.1)
    result = [item async for item in wrapped]
    assert result == [_BOUNDARY_DONE_MSG]


@pytest.mark.asyncio
async def test_child_exception_emits_error_then_done():
    """子生成器异常由边界吞下，改为补 `error` + 唯一 `done`（不再上抛）。

    这是「包装器即流边界」的核心：已发出的 200 流无法再改状态码，
    只能靠帧内 error 通知客户端。
    """
    async def failing():
        yield "before\n\n"
        raise RuntimeError("boom")
        yield "after\n\n"  # pragma: no cover

    wrapped = sse_heartbeat_generator(failing(), interval_sec=0.5)
    result = [item async for item in wrapped]

    assert result == ["before\n\n", _BOUNDARY_ERROR_MSG, _BOUNDARY_DONE_MSG]
    assert "after\n\n" not in result


def test_default_interval_is_15():
    assert DEFAULT_INTERVAL == 15.0


def test_heartbeat_is_sse_comment():
    assert HEARTBEAT_MSG.startswith(":")
    assert HEARTBEAT_MSG.endswith("\n\n")
