"""Task 4 验收 harness - 同进程 ASGI HTTP/SSE 测试。

满足用户原话:"同进程 ASGI HTTP 测试,或启动一个仅用于验收的临时 uvicorn harness,
在该进程启动前完成 monkeypatch,再用 curl 请求。不得修改生产 Workflow 装配。"

本文件是验收 harness,**不修改生产装配**:
- 直接 import 真实 internal_api.router
- 在 ASGI app 内 (httpx.AsyncClient + ASGITransport) monkeypatch _get_resource_center / _get_inquiry_service
- 走真实 FastAPI/Starlette HTTP/SSE 流处理
- 解析 SSE,断言 done.data 8 字段完整

执行:python _accept_sse_harness.py
"""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI


def _make_fake_workflow_state() -> dict:
    """完整 workflow 终态 state,覆盖 ResourceCenter._done_payload 读取的全部键。"""
    return {
        "content_blocks": [
            {"type": "section", "heading": "反向传播概述", "content": "反向传播是训练神经网络的链式法则工程实现。"},
            {"type": "callout", "heading": "核心要点", "content": "复用局部梯度的动态规划。"},
        ],
        "questions": [],
        "response": "已为您生成「反向传播」的技术速览，共 2 个内容块。",
        "error": "",
        "review_status": "pass",
        "repair_attempted": False,
        "fallback_used": False,
        "final_status": "success",
    }


def _make_center():
    from app.centers.resource_center import ResourceCenter
    center = ResourceCenter()
    center.resource_workflow = AsyncMock()
    center.resource_workflow.run = AsyncMock(return_value=_make_fake_workflow_state())
    return center


def _make_inquiry_service_mock():
    """构造的追问输入,完全本地构造,不走真实 LLM/InquiryService.check。"""
    fake = MagicMock()
    fake.resolve.return_value = {
        "topic": "反向传播",
        "context_note": "原始请求: 想学反向传播\n想要公式推导还是直觉讲解？: 先讲直觉再给公式",
        "suggested_types": ["content", "mindmap"],
        "level": "intermediate",
        "goal": "self_study",
    }
    return fake


def _consume_sse(response) -> list[dict]:
    events: list[dict] = []
    buffer = ""
    while True:
        chunk = response.read_chunk()
        if not chunk:
            break
        buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            for line in block.split("\n"):
                if line.startswith("data: "):
                    payload = line[len("data: "):]
                    try:
                        events.append(json.loads(payload))
                    except json.JSONDecodeError:
                        events.append({"_raw": payload})
                    break
    return events


def _parse_raw_sse(raw: str) -> list[dict]:
    """备用 SSE 解析,直接从累积字符串解析。"""
    events: list[dict] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("data: "):
                payload = line[len("data: "):]
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    events.append({"_raw": payload})
                break
    return events


async def run_acceptance():
    from internal_api import router

    app = FastAPI()
    app.include_router(router)
    center = _make_center()
    fake_inquiry = _make_inquiry_service_mock()

    # ═══════════════════════════════════════════════════════════
    # Case 1: /internal/resources/generate 同进程 ASGI HTTP/SSE
    # ═══════════════════════════════════════════════════════════
    print("\n========== CASE 1: /internal/resources/generate ==========")
    with patch("internal_api._get_resource_center", return_value=center):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
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

    print(f"HTTP {response.status_code}  content-type={response.headers.get('content-type')}")
    raw = response.text
    print(f"raw bytes: {len(raw)}")
    events = _parse_raw_sse(raw)
    print(f"events: {len(events)}")
    types_count: dict[str, int] = {}
    for e in events:
        types_count[e.get("type", "?")] = types_count.get(e.get("type", "?"), 0) + 1
    print(f"event types: {types_count}")
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1, f"expect exactly 1 done, got {len(done_events)}"
    data = done_events[0]["data"]
    print(f"done.data keys: {list(data.keys())}")
    for k in ["content_blocks", "questions", "response", "error", "review_status", "repair_attempted", "fallback_used", "final_status"]:
        assert k in data, f"missing key: {k}"
    print(f"content_blocks count: {len(data['content_blocks'])}")
    print(f"first block heading: {data['content_blocks'][0]['heading']!r}")
    print(f"response[:80]: {data['response'][:80]!r}")
    print(f"review_status={data['review_status']!r}  repair_attempted={data['repair_attempted']!r}  fallback_used={data['fallback_used']!r}  final_status={data['final_status']!r}  error={data['error']!r}")
    assert data["content_blocks"], "content_blocks must be non-empty"
    assert data["response"], "response must be non-empty"
    assert data["error"] == "", "error must be empty on success"
    assert data["final_status"] == "success"
    print("CASE 1 PASS")

    # ═══════════════════════════════════════════════════════════
    # Case 2: /internal/inquiry/resolve 同进程 ASGI HTTP/SSE (构造的追问输入)
    # ═══════════════════════════════════════════════════════════
    print("\n========== CASE 2: /internal/inquiry/resolve (constructed input) ==========")
    print("(注: original_message/questions/answers 全部为本脚本内构造的字段,非真实上游追问链路)")
    center2 = _make_center()
    with patch("internal_api._get_inquiry_service", return_value=fake_inquiry), \
         patch("internal_api._get_resource_center", return_value=center2):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
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
                    "student_profile": {"level": "intermediate", "goal": "self_study"},
                },
            )

    print(f"HTTP {response.status_code}  content-type={response.headers.get('content-type')}")
    raw = response.text
    print(f"raw bytes: {len(raw)}")
    events = _parse_raw_sse(raw)
    print(f"events: {len(events)}")
    types_count = {}
    for e in events:
        types_count[e.get("type", "?")] = types_count.get(e.get("type", "?"), 0) + 1
    print(f"event types: {types_count}")
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1, f"expect exactly 1 done, got {len(done_events)}"
    data = done_events[0]["data"]
    print(f"done.data keys: {list(data.keys())}")
    for k in ["content_blocks", "questions", "response", "error", "review_status", "repair_attempted", "fallback_used", "final_status"]:
        assert k in data, f"missing key: {k}"
    assert data["content_blocks"], "content_blocks must be non-empty"
    assert data["error"] == ""
    assert data["final_status"] == "success"
    # 校验 mock inquiry.resolve 被以构造的 original_message 调用
    fake_inquiry.resolve.assert_called_once()
    call_args = fake_inquiry.resolve.call_args
    print(f"inquiry.resolve call_args: args[0]={call_args.args[0]!r}")
    print(f"inquiry.resolve call_args: kwargs['clarified_topic']={call_args.kwargs.get('clarified_topic')!r}")
    assert call_args.args[0] == "想学反向传播", "original_message must be passed to inquiry.resolve"
    assert call_args.kwargs.get("clarified_topic") == "反向传播"
    # 校验 workflow.run 收到 topic + suggested_types[0] + 含 _inquiry_context 的 student_profile
    center2.resource_workflow.run.assert_awaited_once()
    call_state = center2.resource_workflow.run.await_args.args[0]
    print(f"workflow.run state: topic={call_state['topic']!r}, resource_type={call_state['resource_type']!r}, profile_keys={list(call_state['student_profile'].keys())}")
    assert call_state["topic"] == "反向传播"
    assert call_state["resource_type"] == "content", "primary_type should be first suggested_type 'content' (mocked) — but our mock returns ['content', 'mindmap'] so primary is 'content'"
    assert "_inquiry_context" in call_state["student_profile"], "_inquiry_context must be injected into student_profile"
    print(f"_inquiry_context[:80]: {call_state['student_profile']['_inquiry_context'][:80]!r}")
    print("CASE 2 PASS")

    # ═══════════════════════════════════════════════════════════
    # Case 3: Workflow 异常 → SSE 恰好一个 done, error 字段为约定中文
    # ═══════════════════════════════════════════════════════════
    print("\n========== CASE 3: workflow raises → error done ==========")
    center_err = _make_center()
    center_err.resource_workflow.run = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("internal_api._get_resource_center", return_value=center_err):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
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
    print(f"HTTP {response.status_code}")
    raw = response.text
    events = _parse_raw_sse(raw)
    print(f"events: {len(events)}")
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1, f"expect exactly 1 done, got {len(done_events)}"
    data = done_events[0]["data"]
    print(f"done.data: {data}")
    assert data == {"error": "资源生成失败，请稍后重试"}, f"unexpected payload: {data}"
    print("CASE 3 PASS")

    # ═══════════════════════════════════════════════════════════
    # Case 4: workflow mock 提前返回 → 不影响生产装配,验证委派路径
    # (取消消费由离线测试 TestResourceCenterStreamGenerate.test_stream_generate_calls_workflow_run_once 覆盖)
    # ═══════════════════════════════════════════════════════════
    print("\n========== CASE 4: workflow fast-path returns — no side effects ==========")
    print("(取消消费由离线测试 TestResourceCenterStreamGenerate 覆盖 try/finally 兜底,此处仅再次确认委派路径)")
    center_fast = _make_center()
    fast_state = _make_fake_workflow_state()
    fast_state["content_blocks"] = [{"type": "section", "heading": "快速返回", "content": "立刻完成"}]
    fast_state["response"] = "快速生成"
    center_fast.resource_workflow.run = AsyncMock(return_value=fast_state)
    with patch("internal_api._get_resource_center", return_value=center_fast):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/internal/resources/generate",
                json={
                    "user_id": 99,
                    "topic": "快速测试",
                    "student_profile": {"level": "beginner"},
                    "resource_type": "document",
                },
            )
    assert response.status_code == 200
    events = _parse_raw_sse(response.text)
    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    assert done[0]["data"]["response"] == "快速生成"
    assert done[0]["data"]["final_status"] == "success"
    print("CASE 4 PASS")

    print("\n========== ALL 4 CASES PASS ==========")


def main() -> int:
    asyncio.run(run_acceptance())
    return 0


if __name__ == "__main__":
    sys.exit(main())
