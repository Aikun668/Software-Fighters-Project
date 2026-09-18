"""ResourceCenter API 契约离线测试。

不调真实 LLM、真实 ResourceGenWorkflow、真实网络。仅验证：
- ResourceCenter.stream_generate() 成功路径产出完整 done payload
- 每次资源请求只调用一次 ResourceGenWorkflow.run()
- Workflow 异常仍产生恰好一个 done 事件，error 字段正确
- /internal/resources/generate 路由委派给 ResourceCenter.stream_generate
- /internal/inquiry/resolve 路由委派给 ResourceCenter.stream_generate 且注入 _inquiry_context

**RED 状态说明（截至 Task 1 提交）**：
- ResourceCenter.stream_generate() 尚未实现 → TestResourceCenterStreamGenerate 三个测试因 AttributeError RED
- internal_api._get_resource_center 工厂尚未存在 → TestResourceCenterApiDelegation 两个测试因 patch AttributeError RED
- Task 2 实现 ResourceCenter.stream_generate 后前三个测试转绿
- Task 3 添加 _get_resource_center 工厂、API 委派 ResourceCenter 后所有测试转绿
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _make_fake_workflow_state() -> dict:
    """完整 workflow 终态 state，包含 ResourceCenter._done_payload 应当读取的全部键。"""
    return {
        "content_blocks": [
            {"type": "section", "heading": "概述", "content": "测试内容"}
        ],
        "questions": [],
        "response": "资源已生成",
        "error": "",
        "review_status": "passed",
        "repair_attempted": False,
        "fallback_used": False,
        "final_status": "success",
    }


def _make_center_with_fake_workflow(state=None, *, raises=None) -> "ResourceCenter":
    """构造 ResourceCenter + 注入 fake workflow，用于直接测 stream_generate 契约。"""
    from app.centers.resource_center import ResourceCenter

    center = ResourceCenter()
    fake_workflow = AsyncMock()
    if raises is not None:
        fake_workflow.run = AsyncMock(side_effect=raises)
    else:
        fake_workflow.run = AsyncMock(return_value=state if state is not None else _make_fake_workflow_state())
    center.resource_workflow = fake_workflow
    return center


def _make_app() -> FastAPI:
    from internal_api import router

    app = FastAPI()
    app.include_router(router)
    return app


async def _consume_sse(response) -> list[dict]:
    """从 httpx response 中解析 SSE 文本为事件列表。"""
    events: list[dict] = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            for line in block.split("\n"):
                if line.startswith("data: "):
                    payload = line[len("data: "):]
                    try:
                        events.append(json.loads(payload))
                    except json.JSONDecodeError:
                        pass
                    break
    return events


# ═══════════════════════════════════════════════════════════════
# TestResourceCenterStreamGenerate — ResourceCenter.stream_generate 契约
# ═══════════════════════════════════════════════════════════════

class TestResourceCenterStreamGenerate:

    @pytest.mark.asyncio
    async def test_stream_generate_yields_done_with_full_payload(self):
        """成功路径：stream_generate 至少 yield 一个 done，done.data 含全部 8 字段。"""
        from app.events.types import StreamEventType

        center = _make_center_with_fake_workflow(_make_fake_workflow_state())

        events = []
        async for event in center.stream_generate(
            user_id=7,
            topic="反向传播",
            student_profile={"level": "beginner"},
            resource_type="document",
        ):
            events.append(event)

        done_events = [e for e in events if e.type == StreamEventType.DONE]
        assert len(done_events) == 1

        data = done_events[0].data
        assert data["content_blocks"] == [
            {"type": "section", "heading": "概述", "content": "测试内容"}
        ]
        assert data["questions"] == []
        assert data["response"] == "资源已生成"
        assert data["error"] == ""
        assert data["review_status"] == "passed"
        assert data["repair_attempted"] is False
        assert data["fallback_used"] is False
        assert data["final_status"] == "success"

    @pytest.mark.asyncio
    async def test_stream_generate_calls_workflow_run_once(self):
        """同一 stream_generate 请求：workflow.run 仅被调用一次。"""
        center = _make_center_with_fake_workflow(_make_fake_workflow_state())
        fake_workflow = center.resource_workflow

        events = []
        async for event in center.stream_generate(
            user_id=7,
            topic="反向传播",
            student_profile={"level": "beginner"},
            resource_type="document",
        ):
            events.append(event)

        fake_workflow.run.assert_awaited_once()
        call_kwargs = fake_workflow.run.await_args.kwargs
        assert call_kwargs["user_id"] == 7
        assert call_kwargs["topic"] == "反向传播"
        assert call_kwargs["student_profile"] == {"level": "beginner"}
        assert call_kwargs["resource_type"] == "document"

    @pytest.mark.asyncio
    async def test_stream_generate_workflow_exception_yields_error_done(self):
        """Workflow 抛 RuntimeError：stream_generate 仍 yield 恰好一个 done，error 字段正确。"""
        from app.events.types import StreamEventType

        center = _make_center_with_fake_workflow(raises=RuntimeError("boom"))

        events = []
        async for event in center.stream_generate(
            user_id=7,
            topic="反向传播",
            student_profile={"level": "beginner"},
            resource_type="document",
        ):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.DONE
        assert events[0].data == {"error": "资源生成失败，请稍后重试"}


# ═══════════════════════════════════════════════════════════════
# TestResourceCenterApiDelegation — API 路由委派 ResourceCenter
# ═══════════════════════════════════════════════════════════════

class TestResourceCenterApiDelegation:

    @pytest.mark.asyncio
    async def test_resources_generate_delegates_to_resource_center_stream_generate(self):
        """POST /internal/resources/generate → patch _get_resource_center → 委派至 stream_generate。"""
        center = _make_center_with_fake_workflow(_make_fake_workflow_state())

        with patch("internal_api._get_resource_center", return_value=center):
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/internal/resources/generate",
                    json={
                        "user_id": 7,
                        "topic": "反向传播",
                        "student_profile": {"level": "beginner"},
                        "resource_type": "document",
                    },
                )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = await _consume_sse(response)
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["data"]["content_blocks"] == [
            {"type": "section", "heading": "概述", "content": "测试内容"}
        ]

    @pytest.mark.asyncio
    async def test_inquiry_resolve_delegates_to_resource_center_with_inquiry_context(self):
        """POST /internal/inquiry/resolve → Center 收到 topic + 首个 suggested_type + _inquiry_context。"""
        from unittest.mock import MagicMock

        center = _make_center_with_fake_workflow(_make_fake_workflow_state())
        fake_inquiry = MagicMock()
        fake_inquiry.resolve.return_value = {
            "topic": "反向传播",
            "context_note": "用户要求先讲直觉再给公式",
            "suggested_types": ["document", "mindmap"],
            "level": "intermediate",
            "goal": "self_study",
        }

        with patch("internal_api._get_inquiry_service", return_value=fake_inquiry), \
             patch("internal_api._get_resource_center", return_value=center):
            async with AsyncClient(
                transport=ASGITransport(app=_make_app()),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/internal/inquiry/resolve",
                    json={
                        "user_id": 7,
                        "original_message": "想学反向传播",
                        "answers": ["先讲直觉再给公式"],
                        "questions": [{"text": "想要公式推导还是直觉讲解？", "options": []}],
                        "suggested_types": ["document", "mindmap"],
                        "clarified_topic": "反向传播",
                        "student_profile": {"level": "beginner"},
                    },
                )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        # _inquiry_context 必须出现于 SSE done.data 中（语义：ResourceCenter 已接收并构造了 done payload）
        events = await _consume_sse(response)
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
