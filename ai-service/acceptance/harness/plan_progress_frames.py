"""计划进度真实链路 harness（学习闭环化 P0-C）。

为什么单独一个 harness：既有 `plan_endpoints.py` 是**字节存证**口径
（stub `ExerciseAgent.run` 与 `internal_api._get_mock_flag`），只证明「收窄前后响应不变」，
**不证明**「学生动作 → 计划进度更新 → 掌握度变化」这条业务链真能跑。

本文件**不 stub 任何 Center / Service**，跑真实链路：

    POST /internal/plans/{id}/progress
      → PlanCenter.update_progress（真实半衰期掌握度算法，不调 LLM）
      → 返回 updated_step + mastery_updates + 里程碑进度

LLM 若被间接用到，走统一开关 `AI_SERVICE_MOCK_LLM=1`（P0-B 后无需 patch）。

用法（在 ai-service 目录）：
    python -m acceptance.harness.plan_progress_frames after

设计：
- 指纹只取**稳定业务字段**（step_order / topic / mastery old→new / delta），跨环境可复跑；
- 同时断言（不只打指纹）：完成态 mastery 不得下降、资源浏览只给弱信号、计划缺失 → 404；
- 连续跑两次断言指纹一致（同一输入必须可复现）。
"""

import asyncio
import hashlib
import json
import os
import sys

# ⚠️ 必须在 import app.* 之前设置：工厂在构造时读这个开关
os.environ.setdefault("AI_SERVICE_MOCK_LLM", "1")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from internal_api import router  # noqa: E402


def _plan(**over) -> dict:
    base = {
        "id": 7,
        "user_id": 1,
        "status": "active",
        "total_steps": 3,
        "completed_steps": 1,
        "start_date": "2026-09-01",
        "milestones": [{"milestone_id": "m1", "after_step": 2, "description": "第一阶段"}],
    }
    base.update(over)
    return base


def _step(order: int, **over) -> dict:
    base = {
        "id": order,
        "step_order": order,
        "topic": f"主题{order}",
        "knowledge_node_id": f"n{order}",
        "status": "pending",
        "estimated_days": 1,
        "topic_difficulty": 3,
        "review_count": 0,
        "last_review_at": None,
    }
    base.update(over)
    return base


def _steps() -> list[dict]:
    return [_step(1), _step(2), _step(3)]


# (case 名, 期望状态码, 路径, 请求体)
CASES = [
    ("progress_exercise_completed", 200, "/internal/plans/7/progress", {
        "user_id": 1, "step_id": 0, "step_order": 1, "status": "completed",
        "score": 0.8, "activity_type": "exercise", "duration_minutes": 30,
        "plan": _plan(), "steps": _steps(), "masteries": {"n1": 0.5},
    }),
    ("progress_resource_viewed", 200, "/internal/plans/7/progress", {
        # 注意：activity_type 的合法取值是 study/exercise/quiz/review
        # （ProgressUpdateRequest 的 Literal 约束），"study" 才映射到 resource_viewed
        "user_id": 1, "step_id": 0, "step_order": 2, "status": "in_progress",
        "activity_type": "study", "duration_minutes": 10,
        "plan": _plan(), "steps": _steps(), "masteries": {"n2": 0.5},
    }),
    ("progress_plan_missing", 404, "/internal/plans/7/progress", {
        "user_id": 1, "step_id": 0, "step_order": 1, "status": "completed",
        "score": 0.8, "activity_type": "exercise", "duration_minutes": 30,
        "plan": {}, "steps": [], "masteries": {},
    }),
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _fingerprint(payload: dict) -> str:
    """稳定指纹：只含业务字段，跨环境可复跑。"""
    parts = [f"plan_id={payload.get('plan_id')}"]
    step = payload.get("updated_step") or {}
    parts.append(f"step_order={step.get('step_order')}")
    parts.append(f"topic={step.get('topic')}")
    parts.append(f"status={step.get('status')}")
    updates = payload.get("mastery_updates") or {}
    for node in sorted(updates):
        info = updates[node] or {}
        parts.append(
            f"mastery:{node}:{info.get('old_mastery')}->{info.get('new_mastery')}"
            f":{info.get('delta')}:{info.get('event_type')}"
        )
    return "\n".join(parts)


def _check(name: str, status: int, payload: dict) -> list[str]:
    """断言：返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    if name == "progress_plan_missing":
        if status != 404:
            problems.append(f"计划缺失应映射 404，实际 {status}")
        return problems

    if status != 200:
        problems.append(f"status={status}")
        return problems

    step = payload.get("updated_step") or {}
    if not step:
        problems.append("缺少 updated_step")
    updates = payload.get("mastery_updates") or {}
    if not updates:
        problems.append("缺少 mastery_updates（掌握度未被计算）")

    if name == "progress_exercise_completed":
        info = updates.get("n1") or {}
        new_mastery = info.get("new_mastery")
        if new_mastery is not None and new_mastery < 0.5:
            problems.append(f"完成练习后掌握度下降：{new_mastery} < 0.5")
        if info.get("event_type") != "exercise_done":
            problems.append(f"事件类型应为 exercise_done，实际 {info.get('event_type')}")
    elif name == "progress_resource_viewed":
        info = updates.get("n2") or {}
        if info.get("event_type") != "resource_viewed":
            problems.append(f"事件类型应为 resource_viewed，实际 {info.get('event_type')}")
        delta = info.get("delta") or 0
        if abs(delta) > 0.2:
            problems.append(f"资源浏览给了过强信号（delta={delta}）")
    return problems


async def _run_once(client: AsyncClient) -> list[str]:
    blocks: list[str] = []
    for name, expected, path, body in CASES:
        response = await client.post(path, json=body)
        try:
            envelope = response.json()
        except ValueError:
            envelope = {}
        # internal_api 统一信封：{"success": ..., "data": {...}}；错误信封无 data
        payload = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            payload = {}

        problems = _check(name, response.status_code, payload)
        if response.status_code != expected:
            problems.append(f"期望 {expected}，实际 {response.status_code}")

        fingerprint = _fingerprint(payload)
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        blocks.append(
            f"### {name} {path}\n"
            f"status={response.status_code}\n"
            f"problems={problems}\n"
            f"payload={json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
            f"sha256={digest}\n"
            f"{fingerprint}\n"
        )
    return blocks


async def main(label: str) -> int:
    app = _make_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept", timeout=120.0,
    ) as client:
        first = await _run_once(client)
        second = await _run_once(client)

    # 可复现性：同一输入两次运行指纹必须一致
    consistency = "OK" if first == second else "MISMATCH（两次运行结果不同）"

    report = "\n".join(first) + f"\n=== 可复现性：{consistency} ===\n"
    with open(f"_accept_plan_progress_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
