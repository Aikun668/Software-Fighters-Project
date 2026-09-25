"""答疑域收口原始 SSE 存证 harness（未跟踪脚本，不进 pytest）。

同进程 ASGI 打 /internal/tutor/chat，注入固定 stub agent，把整段 SSE 字节原样打印，
附 byte 长度与 sha256，用于收口前（提交 3fe0cc9）与收口后（Task 3 之后）逐字节比对。

自动适配两个时代的装配点，保证两种版本喂进去的是同一组逻辑输入：
- 收口后：patch internal_api._get_tutor_center → 真实 TutorCenter + stub
- 收口前：patch internal_api._get_tutor_agent / _get_profile_agent → stub

用法：python _accept_tutor_sse.py > _accept_tutor_sse_raw.txt
"""

import asyncio
import hashlib
import sys

import internal_api
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from internal_api import router

sys.stdout.reconfigure(encoding="utf-8")

MESSAGES = [{"role": "user", "content": "1+1 等于几？"}]


class _StubTutorAgent:
    def __init__(self, state=None, error=None):
        self._state = state if state is not None else {"response": "", "domain": "ai"}
        self._error = error

    async def run(self, state):
        if self._error is not None:
            raise self._error
        return self._state


class _StubProfileAgent:
    def __init__(self, changed=False, profile=None, error=None):
        self._changed = changed
        self._profile = profile if profile is not None else {}
        self._error = error

    async def extract_and_merge(self, profile_dict, messages):
        if self._error is not None:
            raise self._error
        return {"changed": self._changed, "profile": self._profile}


SCENARIOS = [
    {
        "name": "success",
        "tutor_state": {"response": "答案是 42。", "domain": "ai"},
        "student_profile": {},
        "profile": _StubProfileAgent(),
    },
    {
        "name": "profile_delta",
        "tutor_state": {"response": "好。", "domain": "ai"},
        "student_profile": {"knowledge_base": 50},
        "profile": _StubProfileAgent(changed=True, profile={"weak_points": ["积分"]}),
    },
    {
        "name": "empty_response",
        "tutor_state": {"response": "", "domain": "general"},
        "student_profile": {},
        "profile": _StubProfileAgent(changed=True, profile={"weak_points": ["x"]}),
    },
    {
        "name": "agent_error",
        "tutor_state": None,
        "tutor_error": RuntimeError("boom"),
        "student_profile": {},
        "profile": _StubProfileAgent(),
    },
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _patch_targets(scenario):
    """按当前代码版本选择装配点，返回 (patch 上下文, 描述)。"""
    tutor = _StubTutorAgent(scenario.get("tutor_state"), scenario.get("tutor_error"))
    profile = scenario["profile"]

    if hasattr(internal_api, "_get_tutor_center"):
        from app.centers.tutor_center import TutorCenter

        center = TutorCenter(tutor_agent=tutor, profile_agent=profile)
        center.token_delay = 0.0
        center.chunk_size = 4
        return [
            _patch("_get_tutor_center", center),
        ], "TutorCenter 装配点（收口后）"

    return [
        _patch("_get_tutor_agent", tutor),
        _patch("_get_profile_agent", profile),
    ], "Agent 直连装配点（收口前）"


class _patch:
    def __init__(self, attr, value):
        self.attr = attr
        self.value = value

    def __enter__(self):
        self.original = getattr(internal_api, self.attr)
        setattr(internal_api, self.attr, lambda: self.value)
        return self

    def __exit__(self, *exc):
        setattr(internal_api, self.attr, self.original)
        return False


async def main() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        for scenario in SCENARIOS:
            patchers, mode = _patch_targets(scenario)
            for p in patchers:
                p.__enter__()
            try:
                response = await client.post(
                    "/internal/tutor/chat",
                    json={
                        "user_id": 1,
                        "messages": MESSAGES,
                        "student_profile": scenario["student_profile"],
                    },
                )
            finally:
                for p in reversed(patchers):
                    p.__exit__()

            raw = response.text.encode("utf-8")
            print(f"=== scenario: {scenario['name']} | 装配点: {mode} ===")
            print(f"status={response.status_code}")
            print(f"content-type={response.headers.get('content-type')}")
            print(f"bytes={len(raw)}")
            print(f"sha256={hashlib.sha256(raw).hexdigest()}")
            print("--- raw SSE begin ---")
            print(response.text, end="")
            print("--- raw SSE end ---")
            print()


asyncio.run(main())
