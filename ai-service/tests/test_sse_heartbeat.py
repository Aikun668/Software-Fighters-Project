"""Tests for SSE heartbeat keepalive wrapper."""
import asyncio

import pytest

from app.utils.sse_heartbeat import sse_heartbeat_generator, HEARTBEAT_MSG, DEFAULT_INTERVAL


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
    items = ["data: hello\n\n", "data: world\n\n"]
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
    """Child yields fast enough that no heartbeat fires."""
    items = [f"item{i}\n\n" for i in range(20)]
    wrapped = sse_heartbeat_generator(
        _make_generator(items, delays=[0.01] * 20),
        interval_sec=0.5,
    )
    result = [item async for item in wrapped]
    assert HEARTBEAT_MSG not in result
    assert len(result) == len(items)


@pytest.mark.asyncio
async def test_stops_with_child():
    items = ["only\n\n"]
    wrapped = sse_heartbeat_generator(
        _make_generator(items), interval_sec=0.1
    )
    result = [item async for item in wrapped]
    assert result == items


@pytest.mark.asyncio
async def test_empty_child():
    wrapped = sse_heartbeat_generator(_make_generator([]), interval_sec=0.1)
    result = [item async for item in wrapped]
    assert result == []


@pytest.mark.asyncio
async def test_child_exception_propagates():
    async def failing():
        yield "before\n\n"
        raise RuntimeError("boom")
        yield "after\n\n"  # pragma: no cover

    wrapped = sse_heartbeat_generator(failing(), interval_sec=0.5)
    result = []
    with pytest.raises(RuntimeError, match="boom"):
        async for item in wrapped:
            result.append(item)
    assert "before\n\n" in result
    assert "after\n\n" not in result


def test_default_interval_is_15():
    assert DEFAULT_INTERVAL == 15.0


def test_heartbeat_is_sse_comment():
    assert HEARTBEAT_MSG.startswith(":")
    assert HEARTBEAT_MSG.endswith("\n\n")
