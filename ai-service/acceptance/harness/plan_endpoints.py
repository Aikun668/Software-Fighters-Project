#!/usr/bin/env python3
"""计划域收口字节存证：同进程 ASGI 打 9 个计划端点，输出原始响应体 + sha256。

用法（在 ai-service 目录）：
    python _accept_plan_endpoints.py after

在同一 commit 上重跑应得到完全相同的 sha256；跨「收窄前 / 收窄后」两个 commit
重跑，sha256 全等即证明响应字节零变化。

注意：所有时间戳都用相对锚点（TODAY / NOW）构造，并留 1 小时余量，避免跨日导致
days_idle 漂移；ExerciseAgent.run 被替换为固定输出，绝不触网。
"""

import asyncio
import hashlib
import re
import sys
from datetime import date, datetime, timedelta, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import internal_api
from app.agents.exercise_agent import ExerciseAgent
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from internal_api import router

TODAY = date.today()
NOW = datetime.now(timezone.utc)

# 哈希前把响应体里的一切 ISO 日期替换为 `<DATE>` —— 见主循环里的说明
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
IDLE_ANCHOR = (NOW - timedelta(days=5, hours=1)).isoformat()

FIXED_QUESTIONS = [
    {"question": "固定题 1", "answer": "A", "type": "choice"},
    {"question": "固定题 2", "answer": "B", "type": "choice"},
]


def _install_stubs() -> None:
    internal_api._get_mock_flag = lambda: True

    async def _fixed_run(self, state):
        return {"questions": [dict(q) for q in FIXED_QUESTIONS], "response": ""}

    ExerciseAgent.run = _fixed_run


def _plan(**over) -> dict:
    base = {
        "id": 7,
        "user_id": 1,
        "status": "active",
        "total_steps": 3,
        "completed_steps": 1,
        "start_date": TODAY.isoformat(),
        "milestones": [{"milestone_id": "m1", "after_step": 2, "description": "第一阶段"}],
    }
    base.update(over)
    return base


def _step(order: int, **over) -> dict:
    base = {
        "id": order,
        "step_order": order,
        "topic": "主题",
        "knowledge_node_id": f"n{order}",
        "status": "pending",
        "estimated_days": 1,
        "topic_difficulty": 3,
        "mastery_current": 0.5,
        "review_count": 0,
        "last_review_at": None,
    }
    base.update(over)
    return base


def _steps_three() -> list[dict]:
    return [
        _step(1, topic="变量"),
        _step(2, topic="循环", estimated_days=2),
        _step(3, topic="函数"),
    ]


PAUSED_PLAN = lambda: _plan(  # noqa: E731
    status="paused", total_steps=2, completed_steps=1,
    last_activity_at=IDLE_ANCHOR,
)
PAUSED_STEPS = lambda: [  # noqa: E731
    _step(1, topic="变量", status="paused", topic_difficulty=5),
    _step(2, topic="循环"),
]

CASES = [
    ("today", "/internal/plans/7/today", {
        "plan": _plan(), "steps": _steps_three(), "masteries": {"n2": 0.4},
    }),
    ("progress", "/internal/plans/7/progress", {
        "user_id": 1, "step_id": 0, "step_order": 2, "status": "completed",
        "score": 0.8, "activity_type": "exercise", "duration_minutes": 30,
        "plan": _plan(total_steps=3, completed_steps=0,
                      milestones=[{"milestone_id": "m1", "after_step": 2,
                                   "description": "第一阶段"}]),
        "steps": _steps_three(), "masteries": {"n2": 0.5},
    }),
    ("node-status-change", "/internal/plans/7/node-status-change", {
        "node_id": "n1", "old_status": "pending", "new_status": "forgotten",
        "plan": _plan(total_steps=2, completed_steps=0),
        "steps": [_step(1, topic="变量"), _step(2, topic="循环")],
        "masteries": {"n1": 1.0},
    }),
    ("status", "/internal/plans/7/status", {
        "plan": PAUSED_PLAN(), "steps": PAUSED_STEPS(), "masteries": {"n1": 1.0},
    }),
    ("status-legacy", "/internal/plans/status", {
        "plan": PAUSED_PLAN(), "steps": PAUSED_STEPS(), "masteries": {"n1": 1.0},
    }),
    ("review-schedule", "/internal/plans/7/review-schedule", {
        "days_ahead": 7,
        "steps": [
            _step(1, topic="高紧急", status="completed", mastery_current=0.5),
            _step(2, topic="跳过", status="pending"),
            _step(3, topic="中紧急", status="review", topic_difficulty=1,
                  mastery_current=1.0,
                  last_review_at=(TODAY - timedelta(days=20)).isoformat()),
            _step(4, topic="低紧急", status="completed", topic_difficulty=1,
                  mastery_current=1.0,
                  last_review_at=(TODAY - timedelta(days=8)).isoformat()),
        ],
    }),
    ("complete-step", "/internal/plans/7/complete-step", {
        "step": {"step_order": 5, "topic": "函数", "knowledge_node_id": "n3"},
        "plan": {"completed_steps": 4, "total_steps": 5}, "steps": [],
    }),
    ("regression-warmup", "/internal/plans/7/regression-check", {
        "user_id": 1, "plan": _plan(),
        "steps": [_step(1, topic="变量", status="paused", topic_difficulty=5)],
        "days_idle": 5, "masteries": {"n1": 1.0},
    }),
    ("regression-graded", "/internal/plans/7/regression-check", {
        "user_id": 1, "plan": _plan(),
        "steps": [_step(1, topic="变量", status="paused", knowledge_node_id="n1")],
        "days_idle": 10, "masteries": {"n1": 0.5},
        "answers": [{"topic": "变量", "question_type": "choice",
                     "user_answer": "A", "correct_answer": "A"}],
    }),
]


async def main(label: str) -> int:
    _install_stubs()
    app = FastAPI()
    app.include_router(router)

    blocks = []
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept",
    ) as client:
        for name, path, body in CASES:
            response = await client.post(path, json=body)

            # 日期归一化：请求用相对锚点构造，但**响应体里带服务端当天日期**
            # （`"today": "2026-09-25"`），直接对 raw 取 sha256 会每天漂一次
            # （历轮登记的遗留）。归一化后基准可长期复用，且仍能捕获任何逻辑变化。
            raw = _DATE_RE.sub("<DATE>", response.text)
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            blocks.append(
                f"### {name} {path}\n"
                f"status={response.status_code}\n"
                f"sha256={digest}\n"
                f"{raw}\n"
            )

    report = "\n".join(blocks)
    with open(f"_accept_plan_endpoints_{label}.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
