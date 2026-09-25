"""练习域收口验收 harness：同进程 ASGI 抓取 /exercise/generate 与 /solve 原始 SSE 文本。

不修改生产装配：仅在 harness 进程内 patch `internal_api._get_exercise_center`。
用法（在 ai-service 目录）：
    python _accept_exercise_sse.py > _accept_exercise_sse_raw.txt
"""

import asyncio
import json
import sys

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.centers.exercise_center import ExerciseCenter
from internal_api import router


class _StubExerciseAgent:
    def __init__(self, *, error: Exception | None = None):
        self._error = error

    async def run(self, state: dict) -> dict:
        if self._error is not None:
            raise self._error
        return {"questions": [
            {"question": "TCP 三次握手的第二步是什么？", "type": "choice",
             "choices": ["SYN", "SYN+ACK", "ACK"], "answer": "SYN+ACK"},
        ]}


class _StubSolveAgent:
    def __init__(self, *, error: Exception | None = None):
        self._error = error

    async def run(self, state: dict) -> dict:
        if self._error is not None:
            raise self._error
        return {
            "steps": [{"order": 1, "description": "确认题意"}],
            "solution": "答案是 42。",
            "confidence_score": 0.9,
        }


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        return JSONResponse(status_code=400, content={
            "success": False, "error": msg, "error_code": "INVALID_REQUEST",
        })

    app.include_router(router)
    return app


def _center(
    *, solve_error: Exception | None = None, exercise_error: Exception | None = None,
) -> ExerciseCenter:
    center = ExerciseCenter(
        exercise_agent=_StubExerciseAgent(error=exercise_error),
        solve_agent=_StubSolveAgent(error=solve_error),
    )
    center.plan_progress_delay = 0.0
    center.generate_progress_delay = 0.0
    center.token_delay = 0.0
    return center


async def _dump(client: AsyncClient, label: str, path: str, payload: dict, center) -> None:
    with _patch_center(center):
        response = await client.post(path, json=payload)
    raw = response.text
    print(f"===== {label} =====")
    print(f"HTTP {response.status_code} | content-type: {response.headers.get('content-type')}")
    print(f"raw bytes: {len(raw.encode('utf-8'))}")
    print(raw)
    print()


class _patch_center:
    def __init__(self, center):
        self._center = center
        self._original = None

    def __enter__(self):
        self._original = internal_api._get_exercise_center
        internal_api._get_exercise_center = lambda: self._center

    def __exit__(self, *exc):
        internal_api._get_exercise_center = self._original


async def main() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        await _dump(client, "Case 1: /exercise/generate 成功路径",
                    "/internal/exercise/generate",
                    {"topic": "TCP", "count": 1, "strategy": "review",
                     "difficulty": "medium", "student_profile": {}},
                    _center())
        await _dump(client, "Case 2: /solve 成功路径",
                    "/internal/solve",
                    {"question": "1+1=?", "context": ""},
                    _center())
        await _dump(client, "Case 3: /solve 异常路径",
                    "/internal/solve",
                    {"question": "1+1=?", "context": ""},
                    _center(solve_error=RuntimeError("boom")))
        await _dump(client, "Case 3b: /exercise/generate 异常路径",
                    "/internal/exercise/generate",
                    {"topic": "TCP", "count": 1},
                    _center(exercise_error=RuntimeError("boom")))
        with _patch_center(_center()):
            response = await client.post("/internal/exercise/grade", json={
                "type": "choice", "user_answer": "A", "correct_answer": "A",
                "choices": ["A", "B"], "points": 2,
            })
        print("===== Case 4: /exercise/grade 成功路径 =====")
        print(f"HTTP {response.status_code}")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
