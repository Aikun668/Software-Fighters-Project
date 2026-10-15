"""T4-C 三态结果语义（路由正确/执行成功/产物可用）契约。

关键：final_status 是**审计字段**，留在 CenterResult 上，**不进对外 SSE 契约**。
"""

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
    """final_status 是审计字段（CenterResult 上），**不进对外 SSE done 载荷**——
    后者受 sse_contract.json 基线约束，不得新增键。"""

    @pytest.mark.asyncio
    async def test_final_status_not_in_sse_payload(self):
        # SSE done 的 results[] shape 必须与基线一致：不得出现 final_status
        d = _dispatcher(_StatusCenter())
        r = await _run(d)
        assert "final_status" not in r

    @pytest.mark.asyncio
    async def test_center_result_carries_final_status(self):
        # 审计字段仍在 CenterResult 上，供 routing_audit 读取
        res = CenterResult(mode="resource", intent="resource_gen")
        assert res.final_status == "success"
        res2 = CenterResult(mode="resource", intent="resource_gen", final_status="degraded")
        assert res2.final_status == "degraded"

    @pytest.mark.asyncio
    async def test_payload_keys_present(self):
        d = _dispatcher(_StatusCenter())
        r = await _run(d)
        assert "content_blocks" in r["payload_keys"]
