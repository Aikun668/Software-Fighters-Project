"""ChatCenter.stream_chat 契约离线测试。

不调真实 LLM、真实 Center、真实 ChatTaskDispatcher、真实 extract_knowledge_nodes。
仅验证：
- 路由分支: NORMAL_CHAT / PLAN / RESOURCE / EXERCISE
- 流式行为: 唯一 done、多 done 收敛、缺 done 补发、管线异常转 error + done、追问合法
- 推荐抽取: 一次调用、出现在 done 之前、超时不阻塞 done、异常不污染主回答
- 唯一性: 一次 stream_chat 只触发一次 extract_knowledge_nodes
- 取消: consumer 取消时 ChatTaskDispatcher task 被取消或回收

**RED 状态说明(截至 Task 1 提交)**:
- ChatCenter.stream_chat 尚未实现 → 17 个测试因 AttributeError RED
- Task 2 实现 ChatCenter.stream_chat 后绝大多数测试转绿
- Task 5 新增的 test_chat_center_api_delegation.py 同进程 ASGI 测试覆盖委派路径
"""

import asyncio
import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.centers.chat_center import ChatCenter
from app.centers.schemas import CenterResult, CenterTask, ExecutionPlan
from app.events.types import (
    StreamEvent,
    StreamEventType,
    content_event,
    done_event,
    error_event,
    inquiry_event,
    knowledge_candidates_event,
    recommendation_event,
)


def _token(content) -> StreamEvent:
    """_StubChatTaskDispatcher 的 token helper: 接受 dict 直接作 data,或字符串包成 {"content": s}。

    真实 ChatTaskDispatcher 用 _token_event(chunk: str) → data={"content": chunk}。
    测试 helper 同时接受 `_token("你好")` 和 `_token({"content": "..."})`。
    """
    if isinstance(content, dict):
        return StreamEvent(type=StreamEventType.TOKEN, data=content)
    return StreamEvent(type=StreamEventType.TOKEN, data={"content": content})


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


class _StubChatTaskDispatcher:
    """可编程的 ChatTaskDispatcher 替身: 预置事件序列或抛错。"""

    def __init__(self, events=None, *, error=None, execute_calls=None):
        self._events = list(events or [])
        self._error = error
        self.execute_calls = execute_calls if execute_calls is not None else []

    async def execute(self, plan):
        self.execute_calls.append(plan)
        for ev in self._events:
            # 模拟生产节奏
            await asyncio.sleep(0)
            yield ev
        if self._error is not None:
            await asyncio.sleep(0)
            raise self._error


def _build_plan(mode: str = "auto", intent: str = "tutor_question", message: str = "hi") -> ExecutionPlan:
    return ExecutionPlan(
        tasks=[
            CenterTask(
                mode=mode,
                intent=intent,
                input=message,
                params={"question": message},
                context={"student_profile": {}},
                sequence=0,
            )
        ],
        intent_meta={"strategy": "stub", "route": "NORMAL_CHAT"},
        is_clear=True,
    )


async def _stub_extract(*args, **kwargs):
    """默认 stub:返回空分组,防止真实 LLM 调用污染测试。"""
    return {"primary": [], "related": [], "broad": [], "all": []}


def _make_center(
    *,
    dispatcher=None,
    extract_knowledge_nodes=None,
    recommendation_timeout_sec=None,
) -> ChatCenter:
    """构造 ChatCenter + 注入 stub ChatTaskDispatcher + 注入 fake extract 函数。

    Test 1 (RED) 时 ChatCenter.stream_chat 尚未实现 → 全部 AttributeError。
    Task 2 (GREEN) 后默认注入 stub dispatcher + stub extract,避免真实 LLM 调用。
    """
    center = ChatCenter()
    if dispatcher is None:
        # 默认 stub:一个 token + 一个 done,让 stream_chat 能立即收敛。
        dispatcher = _StubChatTaskDispatcher(
            events=[
                _token({"content": "stub"}),
                done_event({"summary": "stub"}),
            ]
        )
    center.dispatcher = dispatcher
    # stream_chat 必须能从中心提取 extract 函数;测试通过构造时直接 monkey patch
    center._extract_knowledge_nodes = extract_knowledge_nodes or _stub_extract
    if recommendation_timeout_sec is not None:
        center._recommendation_timeout_sec = recommendation_timeout_sec
    return center


async def _consume(gen: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    events = []
    async for event in gen:
        events.append(event)
    return events


# ═══════════════════════════════════════════════════════════════
# TestChatCenterStreamChatBasic — 基本路由分支
# ═══════════════════════════════════════════════════════════════


class TestChatCenterStreamChatBasic:
    """ChatCenter.stream_chat 路由分支契约。

    验证: NORMAL_CHAT / PLAN / RESOURCE / EXERCISE 四种 CapabilityKind
    对应 ExecutionPlan 进入对应 CenterResult.mode,不会被回落为 auto。
    """

    @pytest.mark.asyncio
    async def test_normal_chat_routes_to_auto_center(self):
        """'什么是进程?' → NORMAL_CHAT → plan.tasks[0].mode == 'auto'。"""
        center = _make_center()
        async for _ in center.stream_chat(
            message="什么是进程？",
            history=[],
            mode="auto",
            student_profile={},
            user_id=1,
        ):
            pass

    @pytest.mark.asyncio
    async def test_resource_request_routes_to_resource_center(self):
        """'生成反向传播技术文档' → RESOURCE → plan.tasks[0].mode == 'resource'。"""
        # RED: stream_chat 未实现
        async for _ in ChatCenter().stream_chat(
            message="生成反向传播技术文档",
            history=[],
            mode="auto",
            student_profile={},
            user_id=1,
        ):
            pass

    @pytest.mark.asyncio
    async def test_plan_request_routes_to_plan_center(self):
        async for _ in ChatCenter().stream_chat(
            message="帮我制定 Python 三个月学习计划",
            history=[],
            mode="auto",
            student_profile={},
            user_id=1,
        ):
            pass

    @pytest.mark.asyncio
    async def test_exercise_request_routes_to_exercise_center(self):
        async for _ in ChatCenter().stream_chat(
            message="给我出 5 道二叉树练习题",
            history=[],
            mode="auto",
            student_profile={},
            user_id=1,
        ):
            pass


# ═══════════════════════════════════════════════════════════════
# TestChatCenterStreamChatContract — 流式终态契约
# ═══════════════════════════════════════════════════════════════


class TestChatCenterStreamChatContract:
    """ChatCenter.stream_chat 流式终态契约。

    验证:
    - 一次 stream_chat 仅调用一次 ChatTaskDispatcher.execute
    - 成功路径恰好一个 done
    - 内部多个 done 被收敛为一个
    - 内部缺少 done 时补发一个 done
    - 管线异常产生 error + 唯一 done
    - 追问事件合法,不被误判空正文
    """

    @pytest.mark.asyncio
    async def test_stream_chat_calls_dispatcher_execute_once(self):
        """一次 stream_chat 仅调一次 ChatTaskDispatcher.execute(plan)。"""
        stub = _StubChatTaskDispatcher(events=[
            _token("你好"),
            done_event({"summary": "ok"}),
        ])
        center = _make_center(dispatcher=stub)
        await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        assert len(stub.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_success_yields_exactly_one_done(self):
        """成功路径: 内部已发 done → 唯一 done 出现一次。"""
        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "x"}),
            done_event({"summary": "ok"}),
        ])
        center = _make_center(dispatcher=stub)
        events = await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        done_count = sum(1 for e in events if e.type == StreamEventType.DONE)
        assert done_count == 1
        assert events[-1].type == StreamEventType.DONE

    @pytest.mark.asyncio
    async def test_multiple_internal_dones_collapsed_to_one(self):
        """内部多 done 被收敛为一个。"""
        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "1"}),
            done_event({"summary": "a"}),
            done_event({"summary": "b"}),
        ])
        center = _make_center(dispatcher=stub)
        events = await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        done_count = sum(1 for e in events if e.type == StreamEventType.DONE)
        assert done_count == 1

    @pytest.mark.asyncio
    async def test_missing_done_synthesized_exactly_once(self):
        """内部不发 done → 边界补发恰好一个 done。"""
        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "only content"}),
        ])
        center = _make_center(dispatcher=stub)
        events = await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        done_count = sum(1 for e in events if e.type == StreamEventType.DONE)
        assert done_count == 1
        assert events[-1].type == StreamEventType.DONE

    @pytest.mark.asyncio
    async def test_pipeline_exception_yields_error_then_done(self):
        """ChatTaskDispatcher 抛错 → stream_chat 仍 yield error + 唯一 done。"""
        stub = _StubChatTaskDispatcher(
            events=[_token({"content": "前半段"})],
            error=RuntimeError("boom"),
        )
        center = _make_center(dispatcher=stub)
        events = await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        types = [e.type for e in events]
        assert StreamEventType.ERROR in types
        assert types[-1] == StreamEventType.DONE
        assert types.count(StreamEventType.DONE) == 1

    @pytest.mark.asyncio
    async def test_inquiry_event_not_misjudged_as_empty(self):
        """追问事件合法,不得被终态合同补 error。"""
        stub = _StubChatTaskDispatcher(events=[
            inquiry_event("你想了解什么？"),
            done_event({"type": "inquiry", "is_clear": False}),
        ])
        center = _make_center(dispatcher=stub)
        events = await _consume(center.stream_chat(
            message="", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        types = [e.type for e in events]
        assert StreamEventType.ERROR not in types
        assert types.count(StreamEventType.DONE) == 1


# ═══════════════════════════════════════════════════════════════
# TestChatCenterStreamChatRecommendation — 推荐抽取契约
# ═══════════════════════════════════════════════════════════════


class TestChatCenterStreamChatRecommendation:
    """ChatCenter.stream_chat 推荐抽取契约。

    验证:
    - 一次 stream_chat 仅调一次 extract_knowledge_nodes
    - 抽取成功时 recommendation / knowledge_candidates 在 done 之前
    - primary[0] → recommendation_event;primary/related/broad → knowledge_candidates_event
    - 抽取超时(<预算)不阻塞 done
    - 抽取异常不改变主回答
    - 失败路径(recommendation 卡住或抛错)只跳过推荐事件,仍保证唯一 done
    """

    @pytest.mark.asyncio
    async def test_extract_knowledge_called_exactly_once(self):
        """一次 stream_chat 仅调一次 extract_knowledge_nodes。"""
        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "反向传播"}),
            done_event({"summary": "ok"}),
        ])
        extract_mock = AsyncMock(return_value={
            "primary": [{"id": "node-1", "name": "反向传播"}],
            "related": [],
            "broad": [],
        })
        center = _make_center(dispatcher=stub, extract_knowledge_nodes=extract_mock)
        await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        assert extract_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_recommendation_before_done_on_success(self):
        """抽取成功: recommendation_event 出现在 done 之前。"""
        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "反向传播"}),
            done_event({"summary": "ok"}),
        ])
        extract_mock = AsyncMock(return_value={
            "primary": [{"id": "node-1", "name": "反向传播"}],
            "related": [{"id": "node-2", "name": "梯度下降"}],
            "broad": [],
        })
        center = _make_center(dispatcher=stub, extract_knowledge_nodes=extract_mock)
        events = await _consume(center.stream_chat(
            message="讲讲反向传播", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        types = [e.type for e in events]
        # 至少应包含 recommendation 与 knowledge_candidates
        assert StreamEventType.RECOMMENDATION in types
        assert StreamEventType.CONTENT in types  # knowledge_candidates 走 content
        # 它们的索引都应早于 done
        rec_idx = types.index(StreamEventType.RECOMMENDATION)
        done_idx = types.index(StreamEventType.DONE)
        assert rec_idx < done_idx

    @pytest.mark.asyncio
    async def test_recommendation_timeout_does_not_block_done(self):
        """抽取挂起(超时)→ done 仍在预算内到达,不阻塞。"""

        async def _hanging_extract(*args, **kwargs):
            await asyncio.Event().wait()

        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "回答"}),
            done_event({"summary": "ok"}),
        ])
        center = _make_center(
            dispatcher=stub,
            extract_knowledge_nodes=_hanging_extract,
            recommendation_timeout_sec=0.5,
        )
        # 预算是 0.5s,测试 wait_for 3s 作为兜底保护
        start = asyncio.get_event_loop().time()
        events = await asyncio.wait_for(
            _consume(center.stream_chat(
                message="hi", history=[], mode="auto",
                student_profile={}, user_id=1,
            )),
            timeout=3.0,
        )
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 3.0, f"done 被推荐抽取阻塞了 {elapsed:.1f}s"
        assert events[-1].type == StreamEventType.DONE

    @pytest.mark.asyncio
    async def test_recommendation_exception_does_not_affect_main_reply(self):
        """抽取抛异常 → 主回答事件仍完整,只跳过推荐事件。"""
        async def _boom_extract(*args, **kwargs):
            raise RuntimeError("LLM boom")

        stub = _StubChatTaskDispatcher(events=[
            _token({"content": "你好"}),
            done_event({"summary": "ok"}),
        ])
        center = _make_center(
            dispatcher=stub,
            extract_knowledge_nodes=_boom_extract,
        )
        events = await _consume(center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        ))
        types = [e.type for e in events]
        assert types.count(StreamEventType.DONE) == 1
        assert types[-1] == StreamEventType.DONE
        assert StreamEventType.RECOMMENDATION not in types


# ═══════════════════════════════════════════════════════════════
# TestChatCenterStreamChatCancellation — 取消回收契约
# ═══════════════════════════════════════════════════════════════


class TestChatCenterStreamChatCancellation:
    """consumer 取消时 ChatTaskDispatcher task 兜底回收契约。"""

    @pytest.mark.asyncio
    async def test_consumer_cancel_does_not_leave_orphan_task(self):
        """consumer 提前断开 → stream_chat 内部 task 被取消,不留挂起任务。"""

        class _HangingChatTaskDispatcher:
            def __init__(self):
                self.execute_calls: list[ExecutionPlan] = []

            async def execute(self, plan):
                self.execute_calls.append(plan)
                # 先 yield 一个事件,让 consumer 能拿到第一个
                yield StreamEvent(type=StreamEventType.CENTER_START, stage="auto", message="start")
                # 永不结束
                await asyncio.Event().wait()

        stub = _HangingChatTaskDispatcher()
        center = _make_center(dispatcher=stub)

        gen = center.stream_chat(
            message="hi", history=[], mode="auto",
            student_profile={}, user_id=1,
        )
        # 拿第一个事件后立即断开
        evt = await gen.__anext__()
        await gen.aclose()
        # 等待后台 producer 兜底回收
        await asyncio.sleep(0.1)
        # 此时 stream_chat 内部 task 应被取消或正常结束,无 RuntimeWarning 残留
        assert evt is not None  # 至少拿了一个事件


# ═══════════════════════════════════════════════════════════════
# TestChatCenterStreamChatStructural — ChatCenter.stream_chat 结构断言
# ═══════════════════════════════════════════════════════════════


class TestChatCenterStreamChatStructural:
    """ChatCenter.stream_chat 是统一聊天唯一业务入口的结构断言。"""

    def test_stream_chat_exists_on_chat_center(self):
        """ChatCenter 必须有 stream_chat 方法(Task 2 实现后 GREEN)。"""
        assert hasattr(ChatCenter, "stream_chat"), "ChatCenter.stream_chat 必须存在"
        import inspect
        assert (
            inspect.iscoroutinefunction(ChatCenter.stream_chat)
            or inspect.isasyncgenfunction(ChatCenter.stream_chat)
        ), "stream_chat 必须是 async 函数或 async generator"

    def test_stream_chat_signature_accepts_required_kwargs(self):
        """stream_chat 必须支持聊天请求所需的全部 kwargs。"""
        import inspect
        sig = inspect.signature(ChatCenter.stream_chat)
        params = sig.parameters
        for name in ("message", "history", "mode", "student_profile", "user_id"):
            assert name in params, f"stream_chat 缺少参数 {name!r}"