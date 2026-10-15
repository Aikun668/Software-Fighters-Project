"""T4-B 数据依赖注入契约：Dispatcher 执行带 depends_on 的任务时，下游拿到上游结果。"""

import asyncio

import pytest

from app.centers.chat_task_dispatcher import ChatTaskDispatcher
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan


class _CapturingCenter:
    """捕获 execute 收到的 task（用于断言下游拿到了上游结果）。"""

    def __init__(self, fail=False):
        self.received = []
        self.fail = fail

    async def execute(self, task, on_token=None):
        self.received.append(task)
        if self.fail:
            return CenterResult(
                mode=task.mode, intent=task.intent, event_type="error",
                error="boom", agent="stub", sequence=task.sequence,
            )
        return CenterResult(
            mode=task.mode,
            intent=task.intent,
            payload={"from": task.intent, "upstream_results": task.context.get("upstream_results")},
            agent="stub",
            sequence=task.sequence,
        )


def _dispatcher(fail_exercise=False):
    d = ChatTaskDispatcher()
    d.exercise_center = _CapturingCenter(fail=fail_exercise)
    d.visualization_center = _CapturingCenter()
    d.auto_center = _CapturingCenter()
    d.plan_center = _CapturingCenter()
    d.resource_center = _CapturingCenter()
    return d


class TestDependencyInjection:
    @pytest.mark.asyncio
    async def test_downstream_receives_upstream_payload(self):
        d = _dispatcher()
        t1 = CenterTask(mode="exercise", intent="exercise_gen", input="出题", sequence=0)
        t2 = CenterTask(
            mode="visualization", intent="visualize", input="画图",
            sequence=1, depends_on=[0],
        )
        plan = ExecutionPlan(tasks=[t1, t2], is_clear=True, max_intents=3)

        async for _ in d.execute(plan):
            pass

        # t2 的下游 center 收到了上游结果
        captured = d.visualization_center.received
        assert len(captured) == 1
        ctx = captured[0].context
        up = ctx.get("upstream_results")
        assert up is not None
        assert up[0]["intent"] == "exercise_gen"
        assert "payload" in up[0]

    @pytest.mark.asyncio
    async def test_no_depends_on_gets_no_upstream(self):
        d = _dispatcher()
        t1 = CenterTask(mode="exercise", intent="exercise_gen", input="出题", sequence=0)
        t2 = CenterTask(mode="visualization", intent="visualize", input="画图", sequence=1)
        plan = ExecutionPlan(tasks=[t1, t2], is_clear=True, max_intents=3)

        async for _ in d.execute(plan):
            pass

        captured = d.visualization_center.received
        assert captured[0].context.get("upstream_results") is None

    @pytest.mark.asyncio
    async def test_independent_tasks_run_in_order(self):
        d = _dispatcher()
        t1 = CenterTask(mode="exercise", intent="exercise_gen", input="出题", sequence=0)
        t2 = CenterTask(mode="visualization", intent="visualize", input="画图", sequence=1)
        plan = ExecutionPlan(tasks=[t1, t2], is_clear=True, max_intents=3)

        async for _ in d.execute(plan):
            pass

        # 两个 center 都执行了
        assert len(d.exercise_center.received) == 1
        assert len(d.visualization_center.received) == 1


class TestFailureBlocksDependent:
    @pytest.mark.asyncio
    async def test_upstream_failure_skips_dependent(self):
        d = _dispatcher(fail_exercise=True)
        t1 = CenterTask(mode="exercise", intent="exercise_gen", input="出题", sequence=0)
        t2 = CenterTask(
            mode="visualization", intent="visualize", input="画图",
            sequence=1, depends_on=[0],
        )
        plan = ExecutionPlan(tasks=[t1, t2], is_clear=True, max_intents=3)

        events = []
        async for e in d.execute(plan):
            events.append(e)

        # t1 失败，t2（依赖 t1）应被跳过：t2 的 center 不该收到 execute
        assert len(d.visualization_center.received) == 0
        # 有 skip 语义的 error 事件
        assert any("跳过" in (e.message or "") for e in events if e.type.value == "error")

    @pytest.mark.asyncio
    async def test_upstream_failure_independent_still_runs(self):
        d = _dispatcher(fail_exercise=True)
        t1 = CenterTask(mode="exercise", intent="exercise_gen", input="出题", sequence=0)
        t2 = CenterTask(mode="visualization", intent="visualize", input="画图", sequence=1)  # 无依赖
        plan = ExecutionPlan(tasks=[t1, t2], is_clear=True, max_intents=3)

        async for _ in d.execute(plan):
            pass

        # t1 失败，但 t2 无依赖，应照常执行
        assert len(d.visualization_center.received) == 1

