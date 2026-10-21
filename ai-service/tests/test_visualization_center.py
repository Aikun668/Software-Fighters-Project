"""VisualizationCenter 的 ui-block passthrough（D-014）。

前置 tutor 的回答含 ```ui-block 围栏（= 概念在交互图能力清单内，如卷积/
注意力）时，完整讲解必须随 payload.response 下发——ChatTaskDispatcher 的
extract_ui_blocks_from_payload 才能剥离围栏、转成独立 visualization 事件
（D-004/D-010），用户得到「完整讲解 + 交互图」。无围栏时 payload 不变，
仍走 blocks 摘要通道（同事的 html 图表通道，行为零变化）。
"""

import pytest

from app.agents.visualize.visualize_pipeline import VisualizeResult
from app.centers.visualization_center import VisualizationCenter
from app.centers.schemas import CenterTask, ExecutionPlan
from app.events.types import StreamEventType

CONV_ANSWER = (
    "卷积核在输入网格上按步长滑动，每个位置做一次加权求和：\n\n"
    "```ui-block\n"
    '{"type": "conv_window", "version": 1, '
    '"props": {"inputRows": 5, "inputCols": 5, "kernelSize": 3}}\n'
    "```\n"
)

PLAIN_ANSWER = (
    "快速排序的核心是分治：选一个基准元素，把数组分成小于和大于基准的两部分，"
    "再递归排序两部分。平均时间复杂度 O(n log n)。"
)


class FakeTutorAgent:
    def __init__(self, response: str):
        self._response = response

    async def run(self, state):
        return {"response": self._response}


class FakePipeline:
    """should_visualize=False：跳过 html block 生成，聚焦 passthrough 行为。"""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def run(self, question: str, answer: str):
        self.calls.append((question, answer))
        return VisualizeResult.skip(reason="测试跳过")


def _center(answer: str) -> VisualizationCenter:
    return VisualizationCenter(
        visualize_pipeline=FakePipeline(),
        tutor_agent=FakeTutorAgent(answer),
        use_mock_llm=True,
    )


def _task() -> CenterTask:
    return CenterTask(mode="visualization", intent="visualize", input="用交互图演示卷积")


class TestUiBlockPassthrough:
    @pytest.mark.asyncio
    async def test_tutor_answer_with_fence_becomes_response(self):
        result = await _center(CONV_ANSWER).execute(_task())
        assert result.error is None
        # 完整讲解（含围栏）随 response 下发，dispatcher 侧负责剥离与转事件
        assert result.payload["response"] == CONV_ANSWER
        assert "```ui-block" in result.payload["response"]
        # blocks 通道不受影响
        assert result.payload["blocks"] == []

    @pytest.mark.asyncio
    async def test_short_answer_with_fence_still_passes_through(self):
        """<100 字的回答会被替换后喂给管线，但 passthrough 用原始回答。"""
        short_with_fence = (
            "卷积即滑窗加权求和。\n\n```ui-block\n"
            '{"type": "conv_window", "version": 1, '
            '"props": {"inputRows": 5, "inputCols": 5, "kernelSize": 3}}\n'
            "```\n"
        )
        result = await _center(short_with_fence).execute(_task())
        assert result.payload["response"] == short_with_fence

    @pytest.mark.asyncio
    async def test_answer_without_fence_keeps_payload_unchanged(self):
        """无围栏（概念不在能力清单）→ payload 不带 response，走原摘要通道。"""
        result = await _center(PLAIN_ANSWER).execute(_task())
        assert "response" not in result.payload
        assert result.payload["type"] == "visualization"
        assert result.payload["blocks"] == []


class TestDispatcherFullChain:
    """visualization 中心 + 围栏 passthrough → dispatcher 抽取 → 独立事件。"""

    @pytest.mark.asyncio
    async def test_visualize_intent_yields_conv_window_event(self):
        from app.centers.chat_task_dispatcher import ChatTaskDispatcher

        plan = ExecutionPlan(tasks=[_task()])
        events = []
        async for event in ChatTaskDispatcher(
            visualization_center=_center(CONV_ANSWER)
        ).execute(plan):
            events.append(event)

        types = [e.type.value for e in events]
        assert "visualization" in types, f"passthrough 必须产出 visualization 事件: {types}"

        content = next(e for e in events if e.type.value == "content")
        assert "ui-block" not in content.data["response"], "围栏必须被剥离"
        assert "卷积核在输入网格上按步长滑动" in content.data["response"]
        # visualization 中心不发 token：收尾帧是唯一正文载体，不得带 partial
        assert content.data.get("partial") is None

        viz = next(e for e in events if e.type is StreamEventType.VISUALIZATION)
        assert viz.data["type"] == "conv_window"
        assert viz.data["props"] == {
            "inputRows": 5, "inputCols": 5, "kernelSize": 3, "stride": 1,
        }


class TestAutoCenterSkipsEnhanceWhenFencePresent:
    """D-016：tutor 回答已附 ui-block 围栏（交互图能力清单内的概念）时，
    跳过 Chart.js 图解增强——避免同概念重复出图与 30-45 秒的冗余管线耗时。"""

    @staticmethod
    def _recording_center(calls: list) -> "AutoCenter":
        from app.centers.auto_center import AutoCenter

        class RecordingPipeline:
            async def run(self, question: str, answer: str):
                calls.append((question, answer))
                return VisualizeResult.skip(reason="不应被调用")

        return AutoCenter(visualize_pipeline=RecordingPipeline(), use_mock_llm=True)

    @pytest.mark.asyncio
    async def test_fence_in_answer_skips_chart_pipeline(self):
        calls: list = []
        center = self._recording_center(calls)
        messages = [{"role": "user", "content": "画一张图讲讲卷积"}]
        answer_with_fence = (
            "卷积核在输入上按步长滑动：\n\n```ui-block\n"
            '{"type": "conv_window", "version": 1, '
            '"props": {"inputRows": 5, "inputCols": 5, "kernelSize": 3}}\n'
            "```\n"
        )
        blocks = await center._maybe_visualize(messages, answer_with_fence)
        assert blocks == []
        assert calls == [], "回答含围栏时图解增强管线根本不应启动"

    @pytest.mark.asyncio
    async def test_answer_without_fence_still_runs_pipeline(self):
        """无围栏（概念不在能力清单）→ 行为不变：预过滤通过则管线照常执行。"""
        calls: list = []
        center = self._recording_center(calls)
        messages = [{"role": "user", "content": "画一张图讲讲快速排序的流程"}]
        plain_answer = (
            "快速排序分三步：选基准、分区、递归。整个流程的步骤如下……"
            " partition 过程的对比与变化趋势如图所示。"
        )
        await center._maybe_visualize(messages, plain_answer)
        assert len(calls) == 1, "无围栏时管线应照常执行（回归保护）"
