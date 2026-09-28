"""五种学生状态真实链路 harness（学习闭环化 P2 Task 8）。

为什么单独一个 harness：既有 `plan_progress_frames.py` 只验证「学生动作 → 计划进度 →
掌握度变化」这一条链；`test_p2_task3_learning_snapshot.py` 是**纯函数契约测试**
（直接调 `build_snapshot`，不经过 HTTP 与路由层）。两者都**不证明**「读模型经过
`POST /internal/snapshot` 真实组装后，五种学生状态各自给出正确建议」这条业务链真能跑。

本文件**不 stub 任何 Center / Service**，跑真实链路：

    POST /internal/snapshot
      → snapshot 路由（真实取图谱；取不到则降级为「无图谱」而非 500）
      → learning_snapshot.build_snapshot（纯函数，零 IO）
      → next_action.build_next_action（P1 §五 六规则）
      → 返回 10 键 LearningSnapshot

LLM 若被间接用到，走统一开关 `AI_SERVICE_MOCK_LLM=1`（P0-B 后无需 patch）。

用法（在 ai-service 目录）：
    python -m acceptance.harness.learning_snapshot after

设计：
- 覆盖 P2 §7.2 要求的**五种状态**：新进入课程 / 正在按计划学习 / 练习连续错误 /
  中断一段时间（两种触发：paused 与空闲超期）/ 完成当前节点；
- 断言（不只打指纹），对应 P1 §6.3 的 A3 / A6 / A8：
  - **A3** 新进入课程 → `mastery.value is None` 且 `level == "not_started"`（**不是 0.5**）；
  - **A6** `next_action` 至多一条、只有一个 `action_kind`、`entry` 落在路由白名单内、
        且 `entry` ⊂ 前端 9 条合法路由；`next_action` 从不返回跨域指令；
  - **A8** `freshness.computed_from` / `missing_sources` 如实反映缺失来源。
- 指纹只取**稳定业务字段**（status / reason / level / action_kind / entry），跨环境可复跑；
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

# 试点课程（P2 §7.2 固定范围：ai_intro / 10 节点）。非白名单课程 next_action 必为 null。
PILOT_COURSE = "ai_intro"

# 前端 9 条合法路由（frontend/src/router/index.ts）。A6 的白名单校验对象。
FRONTEND_ENTRIES = frozenset({
    "/", "/resource-center", "/learning-path", "/ai-tutor", "/course-detail",
    "/exercise", "/learning-resource-network", "/learning-analysis", "/question-nav-chat",
})

# P1 §五 冻结的六个 action_kind 与对应 entry（唯一真源：app/services/next_action.py）。
ENTRY_BY_KIND = {
    "resume_plan": "/learning-path",
    "review_current_node": "/learning-path",
    "practice_targeted_questions": "/exercise",
    "check_prerequisite": "/learning-resource-network",
    "study_assigned_resource": "/resource-center",
    "ask_for_explanation": "/ai-tutor",
}

# P1 §五 冻结的三个 dismiss_policy。
DISMISS_POLICIES = frozenset({"snooze", "alternative", "manual_pick"})

ALL_SOURCES = ("active_plan", "mastery", "profile", "graph")

REASONS = frozenset({"current_step_node", "review_due", "weakest", "next_ready"})


def _evidence(node_id: str, ev_type: str, *, rec: str, occ: str, eid: str = "") -> dict:
    """构造 LearningEvidence（P1 §4.1 九必填字段）。"""
    return {
        "evidence_id": eid or f"ev_{rec}",
        "student_id": 1,
        "course_id": PILOT_COURSE,
        "node_id": node_id,
        "type": ev_type,
        "occurred_at": occ,
        "source_action": "exercise",
        "source_record_id": rec,
        "score_or_result": 0.3,
        "confidence": 0.9,
        "effect_hint": None,
        "explanation": f"{ev_type} on {node_id}",
    }


def _step(order: int, node_id: str, status: str, **over) -> dict:
    base = {
        "id": order, "step_order": order, "topic": f"主题{order}",
        "knowledge_node_id": node_id, "status": status,
        "estimated_days": 1, "topic_difficulty": 3, "review_count": 0,
        "last_review_at": None, "resource_id": None,
    }
    base.update(over)
    return base


def _plan(**over) -> dict:
    base = {
        "id": 7, "user_id": 1, "title": "AI 入门计划", "status": "active",
        "total_steps": 2, "completed_steps": 0, "start_date": "2026-09-01",
    }
    base.update(over)
    return base


# (case 名, 期望状态码, 请求体, 该 case 的额外断言闭包)
CASES: list[tuple[str, int, dict, dict]] = [
    # ── 状态 1：新进入课程（无计划、无掌握度、无画像）──
    (
        "state1_new_to_course",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE, "plan": {}, "steps": [],
         "masteries": {}, "recent_evidence": [], "student_profile": {},
         "recent_records": [], "session_analysis": {}},
        {"expect_active_plan": None, "expect_reason": "next_ready",
         "expect_mastery_value": None, "expect_level": "not_started",
         "expect_mastery_source": "none",
         "expect_computed_from": ["graph"],
         "expect_missing": ["active_plan", "mastery", "profile"]},
    ),
    # ── 状态 2：正在按计划学习（当前步骤绑定节点，先修已满足，有指定资源）──
    (
        "state2_following_plan",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE,
         "plan": _plan(completed_steps=0),
         "steps": [_step(1, "ai_overview", "completed", resource_id="res_ai_1"),
                   _step(2, "ml_basics", "in_progress", resource_id="res_ml_1",
                         topic="机器学习基础")],
         "masteries": {"ai_overview": 0.9, "ml_basics": 0.7},
         "recent_evidence": [], "student_profile": {},
         "recent_records": [], "session_analysis": {}},
        {"expect_active_plan_present": True, "expect_reason": "current_step_node",
         "expect_mastery_value": 0.7, "expect_level": "proficient",
         "expect_mastery_source": "node_masteries",
         "expect_action_kind": "study_assigned_resource", "expect_entry": "/resource-center",
         "expect_computed_from": ["active_plan", "mastery", "graph"],
         "expect_missing": ["profile"]},
    ),
    # ── 状态 3：练习连续错误（节点掌握度 learning + 连续 exercise_failed 证据）──
    (
        "state3_repeated_failure",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE, "plan": {}, "steps": [],
         "masteries": {"backprop": 0.5},
         "recent_evidence": [
             _evidence("backprop", "exercise_failed", rec="r1", occ="2026-09-26T10:00:00+00:00"),
             _evidence("backprop", "exercise_failed", rec="r2", occ="2026-09-27T10:00:00+00:00"),
         ],
         "student_profile": {}, "recent_records": [], "session_analysis": {}},
        {"expect_active_plan": None, "expect_reason": "weakest",
         "expect_mastery_value": 0.5, "expect_level": "learning",
         "expect_action_kind": "practice_targeted_questions", "expect_entry": "/exercise"},
    ),
    # ── 状态 4a：中断一段时间（计划 status = paused）──
    (
        "state4a_interrupted_paused",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE,
         "plan": _plan(status="paused"),
         "steps": [_step(1, "ai_overview", "in_progress")],
         "masteries": {"ai_overview": 0.4},
         "recent_evidence": [], "student_profile": {},
         "recent_records": [], "session_analysis": {}},
        {"expect_active_plan_present": True, "expect_interrupted": True,
         "expect_stale": True,
         "expect_action_kind": "resume_plan", "expect_entry": "/learning-path"},
    ),
    # ── 状态 4b：中断一段时间（空闲超 7 天，status 仍为 active）──
    (
        "state4b_interrupted_idle",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE,
         "plan": _plan(status="active", last_activity_at="2026-08-01T00:00:00+00:00"),
         "steps": [_step(1, "ai_overview", "in_progress")],
         "masteries": {"ai_overview": 0.4},
         "recent_evidence": [], "student_profile": {},
         "recent_records": [], "session_analysis": {}},
        {"expect_active_plan_present": True, "expect_interrupted": True,
         "expect_stale": True,
         "expect_action_kind": "resume_plan", "expect_entry": "/learning-path"},
    ),
    # ── 状态 5：完成当前节点（全部步骤终态 → current_step 为 null）──
    (
        "state5_node_completed",
        200,
        {"student_id": 1, "course_id": PILOT_COURSE,
         "plan": _plan(completed_steps=2),
         # last_review_at 留空：本状态考的是「无 open step → next_ready」，不是复习到期。
         "steps": [_step(1, "ai_overview", "completed"),
                   _step(2, "ml_basics", "completed")],
         "masteries": {},
         "recent_evidence": [], "student_profile": {},
         "recent_records": [], "session_analysis": {}},
        {"expect_active_plan_present": True, "expect_current_step_null": True,
         "expect_reason": "next_ready",
         "expect_computed_from": ["active_plan", "graph"],
         "expect_missing": ["mastery", "profile"]},
    ),
    # ── 试点闸门：非白名单课程 → next_action 必为 null（P2 Task 5）──
    (
        "gate_non_pilot_course",
        200,
        {"student_id": 1, "course_id": "course_not_in_pilot", "plan": {}, "steps": [],
         "masteries": {"backprop": 0.5},
         "recent_evidence": [
             _evidence("backprop", "exercise_failed", rec="r9", occ="2026-09-27T10:00:00+00:00"),
         ],
         "student_profile": {}, "recent_records": [], "session_analysis": {}},
        {"expect_next_action_null": True},
    ),
]

# 非白名单 case 用的证据 course_id 需与请求体一致
for _name, _status, _body, _ in CASES:
    if _name == "gate_non_pilot_course":
        for _ev in _body["recent_evidence"]:
            _ev["course_id"] = _body["course_id"]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _check_action(problems: list[str], action: dict | None, *, required: bool) -> None:
    """A6：建议卡硬红线（P1 §五 / §5.3 末「同时只返回 1 条」）。"""
    if action is None:
        if required:
            problems.append("next_action 不应为 null")
        return
    if not isinstance(action, dict):
        problems.append(f"next_action 应为对象，实际 {type(action).__name__}")
        return
    kind = action.get("action_kind")
    if kind not in ENTRY_BY_KIND:
        problems.append(f"action_kind 不在冻结六值内：{kind!r}")
        return
    entry = action.get("entry")
    expected_entry = ENTRY_BY_KIND[kind]
    if entry != expected_entry:
        problems.append(f"entry 与 action_kind 不匹配：{kind} → {entry!r}，应为 {expected_entry!r}")
    if entry not in FRONTEND_ENTRIES:
        problems.append(f"entry 不在前端合法路由内（跨域指令）：{entry!r}")
    policy = action.get("dismiss_policy")
    if policy not in DISMISS_POLICIES:
        problems.append(f"dismiss_policy 非法：{policy!r}")
    # 硬红线：一条建议 = 一个 action_kind + 一个 entry（不得出现第二动作字段）
    for forbidden in ("alternatives", "actions", "options"):
        if forbidden in action:
            problems.append(f"建议卡出现多动作字段：{forbidden!r}")


def _check(name: str, status: int, payload: dict, expect: dict) -> list[str]:
    """断言：返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    if status != 200:
        problems.append(f"status={status}")
        return problems
    if not payload:
        problems.append("空 payload")
        return problems

    # 10 键齐全（P1 §二 冻结形状）
    for key in ("student_id", "course_id", "generated_at", "active_plan", "current_node",
                "mastery", "recent_evidence", "profile_context", "freshness", "next_action"):
        if key not in payload:
            problems.append(f"缺少冻结键：{key}")

    active_plan = payload.get("active_plan")
    current_node = payload.get("current_node")
    mastery = payload.get("mastery") or {}
    freshness = payload.get("freshness") or {}
    action = payload.get("next_action")

    if "expect_active_plan" in expect and active_plan is not None:
        problems.append(f"active_plan 应为 null，实际 {active_plan!r}")
    if expect.get("expect_active_plan_present") and not active_plan:
        problems.append("active_plan 不应为 null")
    if expect.get("expect_current_step_null") and active_plan:
        if active_plan.get("current_step") is not None:
            problems.append(f"全部步骤终态时 current_step 应为 null，实际 {active_plan.get('current_step')!r}")
    if "expect_interrupted" in expect and active_plan:
        if bool(active_plan.get("interrupted")) != expect["expect_interrupted"]:
            problems.append(f"interrupted 应为 {expect['expect_interrupted']}，实际 {active_plan.get('interrupted')!r}")

    if "expect_reason" in expect:
        reason = (current_node or {}).get("reason")
        if reason != expect["expect_reason"]:
            problems.append(f"current_node.reason 应为 {expect['expect_reason']!r}，实际 {reason!r}")
    if current_node is not None and current_node.get("reason") not in REASONS:
        problems.append(f"current_node.reason 非法：{current_node.get('reason')!r}")

    if "expect_mastery_value" in expect:
        want = expect["expect_mastery_value"]
        got = mastery.get("value")
        if want is None:
            if got is not None:
                problems.append(f"A3 新进入课程 mastery.value 应为 None（不是 0.5），实际 {got!r}")
        elif got != want:
            problems.append(f"mastery.value 应为 {want}，实际 {got!r}")
    if "expect_level" in expect:
        if mastery.get("level") != expect["expect_level"]:
            problems.append(f"mastery.level 应为 {expect['expect_level']!r}，实际 {mastery.get('level')!r}")
    if "expect_mastery_source" in expect:
        if mastery.get("source") != expect["expect_mastery_source"]:
            problems.append(f"mastery.source 应为 {expect['expect_mastery_source']!r}，实际 {mastery.get('source')!r}")

    # A3 反向守卫：未学习必须是 null，不得退化成 0.5（P2 Task 1 的旧默认值）
    if mastery.get("level") == "not_started" and mastery.get("value") == 0.5:
        problems.append("A3 违规：not_started 却给出 0.5（旧默认值残留）")

    # A8：freshness 如实反映来源
    if "expect_computed_from" in expect:
        if freshness.get("computed_from") != expect["expect_computed_from"]:
            problems.append(
                f"A8 computed_from 应为 {expect['expect_computed_from']}，实际 {freshness.get('computed_from')!r}"
            )
    if "expect_missing" in expect:
        if freshness.get("missing_sources") != expect["expect_missing"]:
            problems.append(
                f"A8 missing_sources 应为 {expect['expect_missing']}，实际 {freshness.get('missing_sources')!r}"
            )
    if "expect_stale" in expect:
        if bool(freshness.get("stale")) != expect["expect_stale"]:
            problems.append(f"freshness.stale 应为 {expect['expect_stale']}，实际 {freshness.get('stale')!r}")
    # computed_from 与 missing_sources 必须互补且无交集（P1 §2.6）
    computed, missing = freshness.get("computed_from") or [], freshness.get("missing_sources") or []
    if set(computed) & set(missing):
        problems.append(f"A8 computed_from 与 missing_sources 有交集：{set(computed) & set(missing)}")
    if sorted(set(computed) | set(missing)) != sorted(ALL_SOURCES):
        problems.append(f"A8 来源集合不闭合：{computed} ∪ {missing} != {list(ALL_SOURCES)}")
    # computed_from 是 ALL_SOURCES 的**子序列**（过滤掉 missing 的），顺序必须保持一致
    expected_order = [src for src in ALL_SOURCES if src in set(computed)]
    if computed != expected_order:
        problems.append(f"A8 computed_from 顺序未按固定 ALL_SOURCES 输出：{computed!r} != {expected_order!r}")

    # A6：建议卡硬红线 + 试点闸门
    if expect.get("expect_next_action_null"):
        if action is not None:
            problems.append(f"非白名单课程 next_action 应为 null，实际 {action!r}")
    else:
        _check_action(problems, action, required=True)
    if "expect_action_kind" in expect:
        kind = (action or {}).get("action_kind")
        if kind != expect["expect_action_kind"]:
            problems.append(
                f"action_kind 应为 {expect['expect_action_kind']!r}，实际 {kind!r}"
            )
    if "expect_entry" in expect:
        entry = (action or {}).get("entry")
        if entry != expect["expect_entry"]:
            problems.append(f"entry 应为 {expect['expect_entry']!r}，实际 {entry!r}")

    return problems


def _fingerprint(payload: dict) -> str:
    """稳定指纹：只含业务字段，跨环境可复跑。"""
    active_plan = payload.get("active_plan") or {}
    current_node = payload.get("current_node") or {}
    mastery = payload.get("mastery") or {}
    freshness = payload.get("freshness") or {}
    action = payload.get("next_action") or {}
    return "\n".join([
        f"active_plan={'null' if not payload.get('active_plan') else active_plan.get('status')}",
        f"interrupted={active_plan.get('interrupted')}",
        f"current_node={current_node.get('node_id')}:{current_node.get('reason')}",
        f"mastery={mastery.get('value')}:{mastery.get('level')}:{mastery.get('source')}",
        f"computed_from={','.join(freshness.get('computed_from') or [])}",
        f"missing_sources={','.join(freshness.get('missing_sources') or [])}",
        f"stale={freshness.get('stale')}",
        f"action={action.get('action_kind')}:{action.get('entry')}:{action.get('dismiss_policy')}",
    ])


async def _run_once(client: AsyncClient) -> tuple[list[str], list[str]]:
    """返回 (每 case 的 sha256 指纹列表, 完整报告块列表)。

    指纹只含稳定业务字段；`generated_at` 是墙上时钟，不进指纹（否则跨秒必然 MISMATCH）。
    """
    digests: list[str] = []
    blocks: list[str] = []
    for name, expected, body, expect in CASES:
        response = await client.post("/internal/snapshot", json=body)
        try:
            envelope = response.json()
        except ValueError:
            envelope = {}
        # internal_api 统一信封：{"success": ..., "data": {...}}；错误信封无 data
        payload = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            payload = {}
        problems = _check(name, response.status_code, payload, expect)
        if response.status_code != expected:
            problems.append(f"期望 {expected}，实际 {response.status_code}")
        fingerprint = _fingerprint(payload)
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        digests.append(digest)
        blocks.append(
            f"### {name}\n"
            f"status={response.status_code}\n"
            f"problems={problems}\n"
            f"payload={json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
            f"sha256={digest}\n"
            f"{fingerprint}\n"
        )
    return digests, blocks


async def main(label: str) -> int:
    app = _make_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://accept", timeout=120.0,
    ) as client:
        digests1, first = await _run_once(client)
        digests2, second = await _run_once(client)
    # 可复现性：同一输入两次运行**指纹**必须一致（不比 payload 里的墙上时钟）
    consistency = "OK" if digests1 == digests2 else "MISMATCH（两次运行结果不同）"
    report = (
        "=== RUN 1 ===\n" + "\n".join(first)
        + "\n=== RUN 2 ===\n" + "\n".join(second)
        + f"\n=== 可复现性：{consistency} ===\n"
    )
    with open(f"_accept_learning_snapshot_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    failed = [block.split("\n")[0] for block in first if "problems=[]" not in block]
    if consistency != "OK":
        print("!! 两次运行结果不一致")
        return 1
    if failed:
        print(f"!! 有断言失败：{failed}")
        return 1
    print(f"OK：{len(CASES)} 个状态用例全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
