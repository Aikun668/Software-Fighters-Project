"""T4-C 三态结果语义（路由正确/执行成功/产物可用）契约。"""

import asyncio

import pytest

from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan


class _StatusCenter:
    def __init__(self, *, error=None, final_status="success", empty_payload=False):
        self.error = error
        self.final_status = final_status
        self.empty_payload = empty_payload

    async def execute(self, task, on_token=None):
        return CenterResult(
            mode=task.mode,
            intent=task.intent,
            event_type="error" if self.error else "resource",
            payload={} if self.empty_payload else {"content_blocks": [{"type": "text"}]},
            agent="stub",
            sequence=task.sequence,
            error=self.error,
            final_status=self.final_status,
        )


def _dispatcher(center):
    d = ChatTaskDispatcher()
    d.resource_center = center
    d.auto_center = center
    d.plan_center = center
    d.exercise_center = center
    d.visualization_center = center
    return d


async def _run(d, mode="resource", intent="resource_gen"):
    plan = ExecutionPlan(
        tasks=[CenterTask(mode=mode, intent=intent, input="x", sequence=0)],
        is_clear=True,
        max_intents=3,
    )
    done = None
    async for e in d.execute(plan):
        if e.type.value == "done":
            done = e
    return done.data.get("results", [{}])[0]


class TestFinalStatusSemantics:
    @pytest.mark.asyncio
    async def test_success_defaults_to_success(self):
        d = _dispatcher(_StatusCenter())
        r = await _run(d)
        assert r["error"] is None
        assert r["final_status"] == "success"

    @pytest.mark.asyncio
    async def test_error_normalizes_to_error(self):
        # center 返回 error 但 final_status 忘设 → 归一化为 error
        d = _dispatcher(_StatusCenter(error="boom", final_status="success"))
        r = await _run(d)
        assert r["error"] == "boom"
        assert r["final_status"] == "error"

    @pytest.mark.asyncio
    async def test_degraded_preserved(self):
        # 执行成功但产物空 → degraded（不误报 success）
        d = _dispatcher(_StatusCenter(final_status="degraded", empty_payload=True))
        r = await _run(d)
        assert r["error"] is None
        assert r["final_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_payload_keys_present(self):
        d = _dispatcher(_StatusCenter())
        r = await _run(d)
        assert "content_blocks" in r["payload_keys"]
