"""四种边界真实链路 harness（学习闭环化 P2 Task 8）。

为什么单独一个 harness：`learning_snapshot.py` 覆盖 P2 §7.2 的**五种学生状态**（正常路径），
本文件覆盖同一节的**四种边界**——它们都是「正常路径之外，系统仍必须做对」的行为：

    ① 重复提交  POST /internal/evidence/apply 同一 payload 两次 → 第二次必须幂等丢弃（P1 §4.4 规则 1 / A4）
    ② 网络重试  超时后客户端重试同一证据 → 必须仍然只计一次（同上，但 current_mastery 可能已被 Java 落库推进）
    ③ 非法组合  资源域报练习证据 → 必须 400 快速失败，绝不静默记账（P1 §4.3 / A5）
                 （枚举外的 source_action 则在模式边界被 pydantic 拦成 422，同样不得记账）
    ④ 计划失效  plan 为空或步骤不存在 → 必须 404，绝不 500 或瞎算
    （另附「建议拒绝」硬红线：建议卡必须可被前端 dismiss，dismiss_policy 落在冻结三值内）

本文件**不 stub 任何 Center / Service**，跑真实链路：
    POST /internal/evidence/apply   → evidence_contract.apply_evidence（真实校验+幂等）
    POST /internal/plans/{id}/progress → plan_center.update_progress（真实取步骤）
    POST /internal/snapshot         → learning_snapshot.build_snapshot → next_action

⚠️ 幂等表是**模块级进程内状态**（`evidence_contract._seen_keys`）。每个 case 前必须
`reset_seen()`，否则 run2 会把 run1 的记录误判为重复（这本身就是本 harness 要钉的性质）。

用法（在 ai-service 目录）：
    python -m acceptance.harness.plan_closure after
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
from app.services import evidence_contract  # noqa: E402

PILOT_COURSE = "ai_intro"

# P1 §五 冻结：建议卡 dismiss_policy 三值 / action_kind 六值（唯一真源：next_action.py）
DISMISS_POLICIES = frozenset({"snooze", "alternative", "manual_pick"})
ACTION_KINDS = frozenset({
    "resume_plan", "review_current_node", "practice_targeted_questions",
    "check_prerequisite", "study_assigned_resource", "ask_for_explanation",
})
# 一条建议 = 一个 action_kind + 一个 entry，不得出现第二动作字段
MULTI_ACTION_FIELDS = ("alternatives", "actions", "options")


def _evidence(*, node_id: str, ev_type: str, source_action: str, rec: str, eid: str = "") -> dict:
    """构造 LearningEvidence（P1 §4.1）。"""
    return {
        "evidence_id": eid or f"ev_{rec}",
        "student_id": 1,
        "course_id": PILOT_COURSE,
        "node_id": node_id,
        "type": ev_type,
        "occurred_at": "2026-09-27T10:00:00+00:00",
        "source_action": source_action,
        "source_record_id": rec,
        "score_or_result": 0.3,
        "confidence": 0.9,
        "effect_hint": None,
        "explanation": f"{src_phrase(source_action)} 产生 {ev_type} @ {node_id}",
    }


def src_phrase(source_action: str) -> str:
    return {"exercise": "练习", "plan": "计划", "resource": "资源",
            "tutor": "答疑", "manual": "人工"}.get(source_action, source_action)


def _apply_body(ev: dict, *, current_mastery: float) -> dict:
    return {"evidence": ev, "current_mastery": current_mastery}


def _progress_body(*, plan: dict, steps: list, **over) -> dict:
    base = {
        "user_id": 1, "step_id": 0, "step_order": 0, "status": "completed",
        "score": None, "activity_type": "exercise", "duration_minutes": 0,
        "plan": plan, "steps": steps, "masteries": {},
    }
    base.update(over)
    return base


# ── 边界 ① ：重复提交 ──────────────────────────────────────────
# 同一 (source_record_id) 提交两次：第一次记账、第二次丢弃。这是 A4 的最小复现。
DUP_EV = _evidence(node_id="backprop", ev_type="exercise_failed", source_action="exercise", rec="dup_1")

# ── 边界 ② ：网络重试 ──────────────────────────────────────────
# 客户端超时后重试，且**重试时 Java 已把新掌握度落库**（current_mastery 已推进到 0.4）。
# 关键：即便传入值变了，同一 source_record_id 仍必须是「只计一次」，new_mastery 不得再变。
RETRY_EV = _evidence(node_id="backprop", ev_type="exercise_failed", source_action="exercise", rec="retry_1")

# ── 边界 ③ ：非法组合（P1 §4.3 / A5）───────────────────────────
# (resource, exercise_done)：两侧都在冻结枚举内，但组合不被允许 → 由 validate_combination 拒 → 400
ILLEGAL_EV = _evidence(node_id="backprop", ev_type="exercise_done", source_action="resource", rec="bad_1")
# source_action 越出冻结枚举 → 由 pydantic Literal 在模式边界拒 → 422（到不了路由体）
UNKNOWN_ACTION_EV = _evidence(node_id="backprop", ev_type="exercise_done", source_action="telepathy", rec="bad_2")
# manual_correction 携带非数值结果：组合合法、幂等键合法，但在**算掌握度时**才抛错。
# 这是唯一能真正检验「先算后记」的向量（compute_new_mastery 抛错分支）。
MANUAL_BAD_SCORE_EV = _evidence(node_id="backprop", ev_type="manual_correction",
                                source_action="manual", rec="bad_3")
MANUAL_BAD_SCORE_EV["score_or_result"] = "不是数字"

# ── 边界 ⑤ ：无节点归属（保留值 __none__）：记事实但不改掌握度 ──
NONE_EV = _evidence(node_id=evidence_contract.NODE_NONE, ev_type="resource_viewed",
                    source_action="resource", rec="none_1")

# 建议卡场景（复用 learning_snapshot 的「练习连续错误」输入形态）
SNAPSHOT_WEAKEST = {
    "student_id": 1, "course_id": PILOT_COURSE, "plan": {}, "steps": [],
    "masteries": {"backprop": 0.5},
    "recent_evidence": [
        _evidence(node_id="backprop", ev_type="exercise_failed", source_action="exercise", rec="s1"),
        _evidence(node_id="backprop", ev_type="exercise_failed", source_action="exercise", rec="s2"),
    ],
    "student_profile": {}, "recent_records": [], "session_analysis": {},
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


async def _post(client: AsyncClient, path: str, body: dict) -> tuple[int, dict]:
    response = await client.post(path, json=body)
    try:
        envelope = response.json()
    except ValueError:
        envelope = {}
    payload = envelope.get("data") if isinstance(envelope, dict) else None
    return response.status_code, payload if isinstance(payload, dict) else {}


# ── 四条边界的断言实现 ────────────────────────────────────────

async def _case_duplicate_submit(client: AsyncClient) -> tuple[list[str], str]:
    """① 重复提交：第一次 applied=True，第二次 applied=False + duplicate_discarded。"""
    evidence_contract.reset_seen()
    problems: list[str] = []

    s1, first = await _post(client, "/internal/evidence/apply", _apply_body(DUP_EV, current_mastery=0.5))
    s2, second = await _post(client, "/internal/evidence/apply", _apply_body(DUP_EV, current_mastery=0.5))

    if s1 != 200:
        problems.append(f"首次提交应 200，实际 {s1}")
    if s2 != 200:
        problems.append(f"重复提交应 200（P1 §4.4 不报错），实际 {s2}")
    if first.get("applied") is not True:
        problems.append(f"首次 applied 应为 True，实际 {first.get('applied')!r}")
    if first.get("effect") != "mastery_updated":
        problems.append(f"首次 effect 应为 mastery_updated，实际 {first.get('effect')!r}")
    if second.get("applied") is not False:
        problems.append(f"A4 重复提交 applied 应为 False，实际 {second.get('applied')!r}")
    if second.get("effect") != "duplicate_discarded":
        problems.append(f"A4 重复提交 effect 应为 duplicate_discarded，实际 {second.get('effect')!r}")
    # A4 核心：重复提交**不得**再算一次掌握度
    if second.get("new_mastery") is not None:
        problems.append(f"A4 重复提交 new_mastery 应为 None（不得重复计入），实际 {second.get('new_mastery')!r}")
    if second.get("idempotent_key") != first.get("idempotent_key"):
        problems.append("同一 source_record_id 的 idempotent_key 应一致")

    fingerprint = "\n".join([
        f"first={s1}:{first.get('applied')}:{first.get('effect')}:{first.get('new_mastery')}",
        f"second={s2}:{second.get('applied')}:{second.get('effect')}:{second.get('new_mastery')}",
        f"key={first.get('idempotent_key')}",
    ])
    return problems, fingerprint


async def _case_network_retry(client: AsyncClient) -> tuple[list[str], str]:
    """② 网络重试：三次提交（首次 + 两次重试），仅计一次；重试时掌握度已推进仍不得再变。"""
    evidence_contract.reset_seen()
    problems: list[str] = []

    body_first = _apply_body(RETRY_EV, current_mastery=0.5)
    # 模拟「首次响应丢失后 Java 已落库」→ 重试时携带的是**新**掌握度 0.4
    body_retry = _apply_body(RETRY_EV, current_mastery=0.4)

    s1, first = await _post(client, "/internal/evidence/apply", body_first)
    s2, retry1 = await _post(client, "/internal/evidence/apply", body_retry)
    s3, retry2 = await _post(client, "/internal/evidence/apply", body_retry)

    for idx, (status, _payload) in enumerate(((s1, first), (s2, retry1), (s3, retry2)), start=1):
        if status != 200:
            problems.append(f"第 {idx} 次提交应 200，实际 {status}")

    applied_count = sum(1 for p in (first, retry1, retry2) if p.get("applied") is True)
    if applied_count != 1:
        problems.append(f"A4 三次提交应恰好 1 次 applied=True，实际 {applied_count} 次")
    computed = [p.get("new_mastery") for p in (retry1, retry2)]
    if any(v is not None for v in computed):
        problems.append(f"A4 重试不得再算掌握度，实际 new_mastery={computed!r}")
    if retry1.get("effect") != "duplicate_discarded" or retry2.get("effect") != "duplicate_discarded":
        problems.append(f"A4 重试 effect 应为 duplicate_discarded，实际 {retry1.get('effect')!r}/{retry2.get('effect')!r}")
    # 反证：掌握度推进到 0.4 后，mastery_level 如实反映当前值，但 applied 仍为 False
    if retry1.get("mastery_level") != "learning":
        problems.append(f"重试应如实反映传入的 current_mastery=0.4 → learning，实际 {retry1.get('mastery_level')!r}")

    fingerprint = "\n".join([
        f"first={s1}:{first.get('applied')}:{first.get('effect')}:{first.get('new_mastery')}",
        f"r1={s2}:{retry1.get('applied')}:{retry1.get('effect')}:{retry1.get('new_mastery')}",
        f"r2={s3}:{retry2.get('applied')}:{retry2.get('effect')}:{retry2.get('new_mastery')}",
        f"applied_count={applied_count}",
    ])
    return problems, fingerprint


async def _case_illegal_combination(client: AsyncClient) -> tuple[list[str], str]:
    """③ 非法组合：400 / 422 快速失败，且**不污染幂等表**（改正后重提应可正常记账）。

    两种「非法」在两处不同的边界被拦下，必须分别断言（先斩后奏裁决，A5）：
      - **枚举内但不允许的组合**（(resource, exercise_done)）→ 走到
        `evidence_contract.validate_combination` → 400，业务语义错误；
      - **枚举外的 source_action**（"telepathy"）→ 被 pydantic Literal 在**模式边界**
        拦下 → 422，根本到不了路由体。两者都属「快速失败、绝不静默记账」，
        故 422 也是合法拒绝，不得要求它必须是 400。

    第三条是**唯一真正能证伪「先算后记」**的向量：`manual_correction` 携带非数值
    结果，组合合法、幂等键合法，只有 `compute_new_mastery` 会抛错。若实现先
    `mark_seen` 再算（回归），被拒请求就会污染幂等表 —— 而「同一幂等键」必须
    完全一致（含 source_action），否则该否定性断言是空洞的（source_action 改名会
    顺带改掉 key，误绿；reviewer 已钉）。故改正重提时**保留 source_action=manual、
    只把 score_or_result 换成数值**。
    """
    evidence_contract.reset_seen()
    problems: list[str] = []

    s1, body1 = await _post(client, "/internal/evidence/apply",
                            _apply_body(ILLEGAL_EV, current_mastery=0.5))
    s2, body2 = await _post(client, "/internal/evidence/apply",
                            _apply_body(UNKNOWN_ACTION_EV, current_mastery=0.5))
    s3, body3 = await _post(client, "/internal/evidence/apply",
                            _apply_body(MANUAL_BAD_SCORE_EV, current_mastery=0.5))
    if s1 != 400:
        problems.append(f"A5 枚举内非法组合 (resource, exercise_done) 应 400，实际 {s1}")
    if s2 != 422:
        problems.append(f"A5 枚举外 source_action 应在模式边界被拒（422），实际 {s2}")
    if s3 != 400:
        problems.append(f"A5 manual_correction 非数值应在算掌握度时被拒（400），实际 {s3}")
    if body1:
        problems.append(f"400 响应不应带 data，实际 {body1!r}")
    if body2:
        problems.append(f"422 响应不应带 data，实际 {body2!r}")
    if body3:
        problems.append(f"400 响应不应带 data，实际 {body3!r}")

    # 否定性断言：被拒证据不得进幂等表 —— 用**完全相同的幂等键**（同 source_action /
    # 同 source_record_id）重提合法请求，必须 applied=True（若拒绝时已 mark_seen，这里会被误判为重复）。
    legal = _evidence(node_id="backprop", ev_type="manual_correction",
                      source_action="manual", rec="bad_3")
    legal["score_or_result"] = 0.8
    s4, body4 = await _post(client, "/internal/evidence/apply", _apply_body(legal, current_mastery=0.5))
    if s4 != 200 or body4.get("applied") is not True:
        problems.append(f"被拒证据不得污染幂等表：同键改正后重提应 applied=True，实际 {s4}/{body4.get('applied')!r}")
    if body4.get("effect") != "mastery_updated":
        problems.append(f"同键改正后重提 effect 应为 mastery_updated，实际 {body4.get('effect')!r}")

    fingerprint = "\n".join([
        f"illegal_pair={s1}", f"out_of_enum_action={s2}", f"compute_reject={s3}",
        f"recovered={s4}:{body4.get('applied')}:{body4.get('effect')}:{body4.get('new_mastery')}",
    ])
    return problems, fingerprint


async def _case_plan_invalid(client: AsyncClient) -> tuple[list[str], str]:
    """④ 计划失效：无计划 → 404；步骤不存在 → 404。绝不 500、绝不瞎算。"""
    problems: list[str] = []

    s1, body1 = await _post(client, "/internal/plans/7/progress",
                            _progress_body(plan={}, steps=[]))
    s2, body2 = await _post(client, "/internal/plans/7/progress",
                            _progress_body(plan={"id": 7, "status": "active"},
                                           steps=[], step_id=999, step_order=999))

    if s1 != 404:
        problems.append(f"plan 为空应 404，实际 {s1}")
    if s2 != 404:
        problems.append(f"步骤不存在应 404，实际 {s2}")
    if body1:
        problems.append(f"404 响应不应带 data，实际 {body1!r}")
    if body2:
        problems.append(f"404 响应不应带 data，实际 {body2!r}")

    fingerprint = f"no_plan={s1}\nno_step={s2}"
    return problems, fingerprint


async def _case_suggestion_dismissable(client: AsyncClient) -> tuple[list[str], str]:
    """建议拒绝硬红线：建议卡必须落在冻结三值 dismiss_policy 内，且只有一个动作。"""
    problems: list[str] = []
    status, payload = await _post(client, "/internal/snapshot", SNAPSHOT_WEAKEST)
    if status != 200:
        problems.append(f"snapshot 应 200，实际 {status}")
        return problems, f"status={status}"

    action = payload.get("next_action")
    if not isinstance(action, dict):
        problems.append(f"应有建议卡，实际 next_action={action!r}")
        return problems, f"action={action!r}"

    kind = action.get("action_kind")
    policy = action.get("dismiss_policy")
    if kind not in ACTION_KINDS:
        problems.append(f"action_kind 不在冻结六值内：{kind!r}")
    if policy not in DISMISS_POLICIES:
        problems.append(f"建议卡必须可被前端拒绝：dismiss_policy={policy!r} 不在冻结三值内")
    for forbidden in MULTI_ACTION_FIELDS:
        if forbidden in action:
            problems.append(f"建议卡出现多动作字段（违反「同时只返回 1 条」）：{forbidden!r}")

    fingerprint = "\n".join([f"kind={kind}", f"policy={policy}", f"entry={action.get('entry')}"])
    return problems, fingerprint


async def _case_node_none(client: AsyncClient) -> tuple[list[str], str]:
    """无节点归属（保留值 __none__）：记事实、不改掌握度。"""
    evidence_contract.reset_seen()
    problems: list[str] = []
    status, body = await _post(client, "/internal/evidence/apply",
                               _apply_body(NONE_EV, current_mastery=0.5))
    if status != 200:
        problems.append(f"__none__ 应 200，实际 {status}")
    if body.get("applied") is not True:
        problems.append(f"__none__ 应 applied=True，实际 {body.get('applied')!r}")
    if body.get("effect") != "recorded_without_mastery":
        problems.append(f"__none__ effect 应为 recorded_without_mastery，实际 {body.get('effect')!r}")
    if body.get("new_mastery") is not None:
        problems.append(f"__none__ 不得改掌握度，实际 new_mastery={body.get('new_mastery')!r}")
    fingerprint = f"none={status}:{body.get('applied')}:{body.get('effect')}:{body.get('new_mastery')}"
    return problems, fingerprint


# (case 名, 期望边界, 执行闭包)
CASES = [
    ("boundary1_duplicate_submit", "重复提交", _case_duplicate_submit),
    ("boundary2_network_retry", "网络重试", _case_network_retry),
    ("boundary3_illegal_combination", "非法组合(A5)", _case_illegal_combination),
    ("boundary4_plan_invalid", "计划失效", _case_plan_invalid),
    ("boundary5_suggestion_dismissable", "建议拒绝", _case_suggestion_dismissable),
    ("boundary6_node_none", "无归属证据", _case_node_none),
]


async def _run_once(client: AsyncClient) -> tuple[list[str], list[str]]:
    digests: list[str] = []
    blocks: list[str] = []
    for name, label, runner in CASES:
        problems, fingerprint = await runner(client)
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        digests.append(digest)
        blocks.append(
            f"### {name}（{label}）\n"
            f"problems={problems}\n"
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
    consistency = "OK" if digests1 == digests2 else "MISMATCH（两次运行结果不同）"
    report = (
        "=== RUN 1 ===\n" + "\n".join(first)
        + "\n=== RUN 2 ===\n" + "\n".join(second)
        + f"\n=== 可复现性：{consistency} ===\n"
    )
    with open(f"_accept_plan_closure_{label}.txt", "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    failed = [block.split("\n")[0] for block in first if "problems=[]" not in block]
    if consistency != "OK":
        print("!! 两次运行结果不一致")
        return 1
    if failed:
        print(f"!! 有断言失败：{failed}")
        return 1
    print(f"OK：{len(CASES)} 个边界用例全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "after")))
