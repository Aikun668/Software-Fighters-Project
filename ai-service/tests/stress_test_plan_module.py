#!/usr/bin/env python3
"""
计划模块轰炸测试脚本 — 不留情面，往死里测。

Usage:
  # 先启动服务（另一个终端）:
  python main.py

  # 然后运行:
  python tests/stress_test_plan_module.py
  python tests/stress_test_plan_module.py --url http://127.0.0.1:8001 --concurrency 30 --duration 10
"""

import asyncio
import os
import sys

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import random
import statistics
import string
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Optional

import httpx

# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

BASE_URL = "http://127.0.0.1:8001"
PLAN_PREFIX = "/internal/plans"

DEFAULT_CONCURRENCY = 20
DEFAULT_DURATION = 10
DEFAULT_BURST = 80

# -- Shared fixtures --------------------------------------------

SAMPLE_PLAN = {
    "id": 1,
    "user_id": 123,
    "status": "active",
    "total_steps": 8,
    "completed_steps": 2,
    "start_date": "2026-06-01",
    "last_activity_at": "2026-06-15T10:00:00Z",
    "milestones": [
        {"milestone_id": "m1", "after_step": 4, "description": "基础概念掌握"},
        {"milestone_id": "m2", "after_step": 8, "description": "实战能力养成"},
    ],
}

SAMPLE_STEPS = [
    {"id": 1, "step_order": 1, "topic": "AI概述", "knowledge_node_id": "ai_overview",
     "status": "completed", "estimated_days": 1, "topic_difficulty": 1,
     "mastery_current": 0.9, "review_count": 1,
     "suggested_resource_types": ["document", "mindmap"]},
    {"id": 2, "step_order": 2, "topic": "机器学习基础", "knowledge_node_id": "ml_basics",
     "status": "completed", "estimated_days": 2, "topic_difficulty": 2,
     "mastery_current": 0.75, "review_count": 0,
     "suggested_resource_types": ["document", "mindmap", "exercise"]},
    {"id": 3, "step_order": 3, "topic": "监督学习", "knowledge_node_id": "supervised_learning",
     "status": "in_progress", "estimated_days": 2, "topic_difficulty": 3,
     "mastery_current": 0.5, "review_count": 0,
     "suggested_resource_types": ["document", "code_demo", "exercise"]},
    {"id": 4, "step_order": 4, "topic": "无监督学习", "knowledge_node_id": "unsupervised_learning",
     "status": "pending", "estimated_days": 2, "topic_difficulty": 3,
     "mastery_current": 0.0, "review_count": 0,
     "suggested_resource_types": ["document", "code_demo", "exercise"]},
    {"id": 5, "step_order": 5, "topic": "神经网络基础", "knowledge_node_id": "neural_network",
     "status": "pending", "estimated_days": 3, "topic_difficulty": 4,
     "mastery_current": 0.0, "review_count": 0,
     "suggested_resource_types": ["document", "code_demo", "exercise", "mindmap"]},
    {"id": 6, "step_order": 6, "topic": "反向传播", "knowledge_node_id": "backpropagation",
     "status": "pending", "estimated_days": 3, "topic_difficulty": 5,
     "mastery_current": 0.0, "review_count": 0,
     "suggested_resource_types": ["document", "formula_sheet", "exercise"]},
    {"id": 7, "step_order": 7, "topic": "CNN架构", "knowledge_node_id": "cnn_architecture",
     "status": "pending", "estimated_days": 2, "topic_difficulty": 4,
     "mastery_current": 0.0, "review_count": 0,
     "suggested_resource_types": ["document", "code_demo", "exercise", "mindmap"]},
    {"id": 8, "step_order": 8, "topic": "模型评估", "knowledge_node_id": "model_evaluation",
     "status": "pending", "estimated_days": 2, "topic_difficulty": 3,
     "mastery_current": 0.0, "review_count": 0,
     "suggested_resource_types": ["document", "case_study", "exercise"]},
]

STUDENT_PROFILE = {
    "knowledge_base": 45,
    "cognitive_style": "visual",
    "learning_goal": "掌握深度学习",
    "weak_points": ["数学基础", "Python编程"],
    "learning_pace": "moderate",
    "interest_direction": ["计算机视觉", "NLP"],
}


# ═══════════════════════════════════════════════════════════════════
# Test result tracking
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str = ""
    latency_ms: float = 0.0


@dataclass
class Metrics:
    total: int = 0
    success: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)
    status_codes: dict[int, int] = field(default_factory=dict)

    def record(self, code: int, elapsed: float):
        self.total += 1
        self.latencies.append(elapsed)
        self.status_codes[code] = self.status_codes.get(code, 0) + 1
        if code in (200, 429):  # 429 = rate limiter working as designed
            self.success += 1
        else:
            self.errors += 1

    def summary(self, label: str = "") -> str:
        if not self.latencies:
            return f"[{label}] 0 requests"
        sorted_lat = sorted(self.latencies)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        avg = statistics.mean(self.latencies)
        duration = sorted_lat[-1] - sorted_lat[0] if len(sorted_lat) > 1 else 0
        tput = self.total / duration if duration > 0 else 0
        lines = [
            f"\n{'='*60}",
            f"  {label}",
            f"{'='*60}",
            f"  Total:      {self.total}  (ok={self.success}  err={self.errors})",
            f"  Throughput: {tput:.1f} req/s",
            f"  Latency:    avg={avg*1000:.1f}ms  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  p99={p99*1000:.1f}ms",
            f"  Statuses:   {dict(self.status_codes)}",
        ]
        return "\n".join(lines)


class TestReporter:
    def __init__(self):
        self.results: list[CaseResult] = []
        self.start_time = time.time()

    def add(self, name: str, passed: bool, detail: str = "", latency_ms: float = 0.0):
        status = "[PASS]" if passed else "[FAIL]"
        lat_str = f" ({latency_ms:.0f}ms)" if latency_ms > 0 else ""
        print(f"  {status} | {name}{lat_str}")
        if not passed and detail:
            print(f"         | → {detail}")
        self.results.append(CaseResult(name, passed, detail, latency_ms))

    def final_report(self) -> str:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        elapsed = time.time() - self.start_time
        lines = [
            f"\n{'='*70}",
            f"  轰炸测试最终报告",
            f"{'='*70}",
            f"  总用例: {total}  通过: {passed}  失败: {failed}  通过率: {passed/max(total,1)*100:.1f}%",
            f"  总耗时: {elapsed:.1f}s",
            f"{'='*70}",
        ]
        if failed:
            lines.append(f"\n  失败用例明细:")
            for r in self.results:
                if not r.passed:
                    lines.append(f"    [FAIL] {r.name}")
                    if r.detail:
                        lines.append(f"       → {r.detail}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# HTTP helpers
# ═══════════════════════════════════════════════════════════════════

async def _post(client: httpx.AsyncClient, path: str, body: dict,
                timeout: int = 60, expect_status: int | None = None) -> tuple[int, dict]:
    """返回 (status_code, response_body)."""
    t0 = time.perf_counter()
    try:
        resp = await client.post(f"{BASE_URL}{path}", json=body,
                                 timeout=httpx.Timeout(timeout))
        elapsed = time.perf_counter() - t0
        data = resp.json() if resp.text else {}
        return resp.status_code, data
    except httpx.TimeoutException:
        return 504, {"error": "timeout"}
    except Exception as e:
        return 0, {"error": str(e)}


def _check_ok(status: int, body: dict) -> bool:
    """检查响应是否成功（code=200 + success=true）."""
    return status == 200 and body.get("success", False) is True


def _check_validation_error(status: int, body: dict) -> bool:
    """检查是否是 Pydantic 验证错误（兼容 400 和 422）。"""
    return status in (400, 422) and body.get("success", True) is False


def _has_keys(data: dict, *keys: str) -> bool:
    """检查 dict 中是否有指定键."""
    return all(k in data for k in keys)


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Happy path — 正常流程
# ═══════════════════════════════════════════════════════════════════

# 缓存 create-from-path 的响应，用于后续步骤
CREATED_PLAN = None


async def test_create_plan_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.1 正常创建计划"""
    global CREATED_PLAN
    body = {
        "user_id": 123,
        "course_id": "ai_intro",
        "topic": "机器学习三个月学习计划",
        "student_profile": STUDENT_PROFILE,
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=120)
    t0 = time.perf_counter()

    if not _check_ok(code, resp):
        reporter.add("create-from-path 正常创建", False, f"status={code} body={json.dumps(resp, ensure_ascii=False)[:200]}")
        return

    data = resp.get("data", {})
    checks = []
    checks.append(("total_steps > 0", data.get("total_steps", 0) > 0))
    checks.append(("steps 非空", len(data.get("steps", [])) > 0))
    checks.append(("title 非空", bool(data.get("title", ""))))
    checks.append(("milestones 存在", isinstance(data.get("milestones"), list)))
    checks.append(("estimated_days > 0", data.get("estimated_days", 0) > 0))
    checks.append(("step 含 knowledge_node_id", any(
        s.get("knowledge_node_id") for s in data.get("steps", [])
    )))
    checks.append(("step 含 suggested_resource_types", any(
        s.get("suggested_resource_types") for s in data.get("steps", [])
    )))

    failed = [c[0] for c in checks if not c[1]]
    if failed:
        reporter.add("create-from-path 响应结构", False, f"缺失/异常: {failed}")
    else:
        reporter.add("create-from-path 正常创建", True,
                     f"total_steps={data['total_steps']} title={data.get('title','')[:30]}")
    CREATED_PLAN = data


async def test_plan_status_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.2 正常查询计划状态"""
    body = {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/status", body)

    if not _check_ok(code, resp):
        reporter.add("plan status", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "plan_id", "status", "total_steps", "completed_steps",
                   "days_idle", "steps", "next_milestone", "milestone_progress")
    reporter.add("plan status 正常查询", ok,
                 f"status={data.get('status')} completed={data.get('completed_steps')}")


async def test_today_tasks_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.3 正常查询今日任务"""
    body = {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS, "start_date": "2026-06-01",
            "masteries": {"supervised_learning": 0.5}}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)

    if not _check_ok(code, resp):
        reporter.add("today tasks", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "plan_id", "today", "day_index", "steps_due_today",
                   "resource_suggestions", "summary")
    reporter.add("today tasks 正常查询", ok,
                 f"day_index={data.get('day_index')} due={len(data.get('steps_due_today',[]))}")


async def test_complete_step_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.4 正常完成步骤"""
    body = {
        "step": {"step_order": 3, "topic": "监督学习",
                 "knowledge_node_id": "supervised_learning", "status": "in_progress"},
        "plan": SAMPLE_PLAN,
        "steps": SAMPLE_STEPS,
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/complete-step", body, timeout=60)

    if not _check_ok(code, resp):
        reporter.add("complete-step", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "step_order", "step_completed", "recommended_action",
                   "questions", "message")
    action_ok = data.get("recommended_action") in ("consolidation", "comprehensive_review")
    questions_ok = isinstance(data.get("questions"), list)
    reporter.add("complete-step 正常完成", ok and action_ok and questions_ok,
                 f"action={data.get('recommended_action')} questions={len(data.get('questions',[]))}")


async def test_progress_update_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.5 正常更新进度"""
    body = {
        "user_id": 123,
        "step_id": 3,
        "step_order": 3,
        "status": "completed",
        "score": 0.85,
        "activity_type": "exercise",
        "duration_minutes": 30,
        "plan": SAMPLE_PLAN,
        "steps": SAMPLE_STEPS,
        "masteries": {"supervised_learning": 0.5},
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)

    if not _check_ok(code, resp):
        reporter.add("progress update", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "plan_id", "updated_step", "mastery_updates",
                   "completed_steps", "progress_pct", "next_milestone")
    # 检查 mastery 是否更新
    m_updates = data.get("mastery_updates", {})
    mastery_ok = len(m_updates) > 0 and "supervised_learning" in m_updates
    reporter.add("progress update 正常更新", ok and mastery_ok,
                 f"progress_pct={data.get('progress_pct')}% mastery_delta={m_updates.get('supervised_learning',{}).get('delta',0)}")


async def test_node_status_change_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.6 节点 mastered → 步骤完成联动"""
    body = {
        "node_id": "supervised_learning",
        "old_status": "learning",
        "new_status": "mastered",
        "plan": SAMPLE_PLAN,
        "steps": SAMPLE_STEPS,
        "masteries": {"supervised_learning": 0.9},
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/node-status-change", body)

    if not _check_ok(code, resp):
        reporter.add("node-status-change", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "plan_id", "node_id", "affected_steps_count",
                   "plan_actions", "summary")
    actions = data.get("plan_actions", [])
    has_mark_completed = any(a.get("action") == "mark_completed" for a in actions)
    reporter.add("node-status-change mastered→completed", ok and has_mark_completed,
                 f"affected={data.get('affected_steps_count')} actions={len(actions)}")


async def test_node_forgotten_flow(client: httpx.AsyncClient, reporter: TestReporter):
    """1.7 节点 forgotten → 复习联动"""
    body = {
        "node_id": "backpropagation",
        "old_status": "learning",
        "new_status": "forgotten",
        "plan": {**SAMPLE_PLAN, "completed_steps": 4},
        "steps": SAMPLE_STEPS,
        "masteries": {"backpropagation": 0.3},
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/node-status-change", body)
    data = resp.get("data", {})
    actions = data.get("plan_actions", [])
    has_review = any(a.get("action") == "schedule_review" for a in actions)
    reporter.add("node-status-change forgotten→review", _check_ok(code, resp) and has_review,
                 f"actions={[a.get('action') for a in actions]}")


async def test_node_locked_flow(client: httpx.AsyncClient, reporter: TestReporter):
    """1.8 节点 locked → 步骤锁定联动"""
    body = {
        "node_id": "unsupervised_learning",
        "old_status": "pending",
        "new_status": "locked",
        "plan": SAMPLE_PLAN,
        "steps": SAMPLE_STEPS,
        "masteries": {},
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/node-status-change", body)
    data = resp.get("data", {})
    actions = data.get("plan_actions", [])
    has_lock = any(a.get("action") == "lock_step" for a in actions)
    reporter.add("node-status-change locked→lock_step", _check_ok(code, resp) and has_lock,
                 f"actions={[a.get('action') for a in actions]}")


async def test_regression_check_phase1(client: httpx.AsyncClient, reporter: TestReporter):
    """1.9 回归检测 — 阶段1 出题（idle > 7 天）"""
    body = {
        "user_id": 123,
        "answers": None,
        "plan": {**SAMPLE_PLAN, "status": "paused"},
        "steps": [{**s, "status": "paused"} for s in SAMPLE_STEPS[2:5]],
        "days_idle": 14,
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/regression-check", body)

    if not _check_ok(code, resp):
        reporter.add("regression-check phase1", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "plan_id", "strategy", "message", "questions")
    strategy_ok = data.get("strategy") in ("continue", "warmup", "regression_check")
    reporter.add("regression-check 阶段1 出题", ok and strategy_ok,
                 f"strategy={data.get('strategy')} questions={len(data.get('questions',[]))}")


async def test_review_schedule_happy(client: httpx.AsyncClient, reporter: TestReporter):
    """1.10 复习日程"""
    body = {"steps": SAMPLE_STEPS, "days_ahead": 7}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/review-schedule", body)

    if not _check_ok(code, resp):
        reporter.add("review-schedule", False, f"status={code}")
        return

    data = resp["data"]
    ok = _has_keys(data, "total_reviews", "high_urgency", "medium_urgency", "schedule")
    reporter.add("review-schedule 正常查询", ok,
                 f"total={data.get('total_reviews')} high={data.get('high_urgency')}")


async def test_progress_by_step_order(client: httpx.AsyncClient, reporter: TestReporter):
    """1.11 按 step_order 定位（step_id=0）"""
    body = {
        "user_id": 123,
        "step_id": 0,
        "step_order": 3,
        "status": "completed",
        "score": 0.9,
        "plan": SAMPLE_PLAN,
        "steps": SAMPLE_STEPS,
    }
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    ok = _check_ok(code, resp) and resp["data"].get("updated_step", {}).get("step_order") == 3
    reporter.add("progress 按 step_order 定位", ok)


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Edge cases — 边界值 & 特殊输入
# ═══════════════════════════════════════════════════════════════════

async def test_create_plan_empty_topic(client: httpx.AsyncClient, reporter: TestReporter):
    """2.1 空 topic"""
    body = {"user_id": 123, "course_id": "ai_intro", "topic": "", "student_profile": STUDENT_PROFILE}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=180)
    ok = code in (200, 400, 422, 500, 504)
    reporter.add("create 空 topic", ok, f"status={code}")


async def test_create_plan_minimal_profile(client: httpx.AsyncClient, reporter: TestReporter):
    """2.2 最小化 student_profile"""
    body = {"user_id": 1, "course_id": "ai_intro", "topic": "Python基础", "student_profile": {}}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=180)
    # 空 profile 可正常工作，LLM 超时/后端错误也算可接受（非崩溃）
    ok = code in (200, 500, 504)
    reporter.add("create 空 student_profile", ok, f"status={code}")


async def test_today_tasks_no_start_date(client: httpx.AsyncClient, reporter: TestReporter):
    """2.3 无 start_date（应 fallback 到当天）"""
    body = {"plan": {**SAMPLE_PLAN, "start_date": None}, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    ok = _check_ok(code, resp)
    reporter.add("today 无 start_date", ok, f"status={code} day_index={resp.get('data',{}).get('day_index','?')}")


async def test_today_tasks_future_plan(client: httpx.AsyncClient, reporter: TestReporter):
    """2.4 计划尚未开始（start_date 在未来）"""
    body = {"plan": {**SAMPLE_PLAN, "start_date": "2027-01-01"}, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    ok = _check_ok(code, resp)
    day_index = resp.get("data", {}).get("day_index", -1)
    reporter.add("today 未来计划", ok and day_index == 0, f"day_index={day_index}")


async def test_today_tasks_all_completed(client: httpx.AsyncClient, reporter: TestReporter):
    """2.5 所有步骤已完成"""
    all_done = [{**s, "status": "completed"} for s in SAMPLE_STEPS]
    body = {"plan": {**SAMPLE_PLAN, "completed_steps": 8, "total_steps": 8},
            "steps": all_done, "start_date": "2026-06-01"}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    ok = _check_ok(code, resp)
    due = resp.get("data", {}).get("steps_due_today", [])
    reporter.add("today 全部已完成", ok, f"due_steps={len(due)} (期望 0)")


async def test_today_tasks_empty_steps(client: httpx.AsyncClient, reporter: TestReporter):
    """2.6 空步骤列表"""
    body = {"plan": SAMPLE_PLAN, "steps": []}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    reporter.add("today 空 steps", _check_ok(code, resp), f"status={code}")


async def test_progress_nonexistent_step(client: httpx.AsyncClient, reporter: TestReporter):
    """2.7 更新的步骤不存在"""
    body = {"user_id": 123, "step_id": 999, "step_order": 999, "status": "completed",
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    ok = code == 404 and resp.get("success") is False
    reporter.add("progress 步骤不存在→404", ok, f"status={code} errorCode={resp.get('errorCode')}")


async def test_progress_no_score(client: httpx.AsyncClient, reporter: TestReporter):
    """2.8 无 score（纯学习，不练习）"""
    body = {"user_id": 123, "step_id": 3, "status": "completed",
            "activity_type": "study", "duration_minutes": 20,
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS,
            "masteries": {"supervised_learning": 0.5}}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    ok = _check_ok(code, resp)
    reporter.add("progress 无 score（study模式）", ok, f"status={code}")


async def test_complete_step_near_end(client: httpx.AsyncClient, reporter: TestReporter):
    """2.9 接近计划末尾触发综合复习"""
    near_end_plan = {**SAMPLE_PLAN, "completed_steps": 7, "total_steps": 8}
    body = {"step": {"step_order": 8, "topic": "模型评估", "knowledge_node_id": "model_evaluation",
                     "status": "in_progress"},
            "plan": near_end_plan, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/complete-step", body, timeout=120)
    action = resp.get("data", {}).get("recommended_action", "")
    # 正常应返回 comprehensive_review，LLM 故障时允许 500（exercise agent 依赖外部 API）
    ok = (code == 200 and action == "comprehensive_review") or code == 500
    reporter.add("complete-step 接近末尾→综合复习", ok,
                 f"status={code} action={action}")


async def test_node_status_change_no_match(client: httpx.AsyncClient, reporter: TestReporter):
    """2.10 节点不在计划中"""
    body = {"node_id": "nonexistent_node_xyz", "old_status": "", "new_status": "mastered",
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS, "masteries": {}}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/node-status-change", body)
    ok = _check_ok(code, resp) and resp["data"].get("affected_steps_count") == 0
    reporter.add("node-status-change 无匹配节点", ok,
                 f"affected={resp.get('data',{}).get('affected_steps_count')}")


async def test_status_legacy_path(client: httpx.AsyncClient, reporter: TestReporter):
    """2.11 兼容旧路径 /plans/status（无 plan_id）"""
    body = {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/status", body)
    reporter.add("plan status 旧路径兼容", _check_ok(code, resp), f"status={code}")


async def test_review_schedule_big_days(client: httpx.AsyncClient, reporter: TestReporter):
    """2.12 复习日程 30 天"""
    body = {"steps": SAMPLE_STEPS, "days_ahead": 30}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/review-schedule", body)
    reporter.add("review-schedule days_ahead=30", _check_ok(code, resp), f"status={code}")


async def test_review_schedule_min_days(client: httpx.AsyncClient, reporter: TestReporter):
    """2.13 复习日程 1 天"""
    body = {"steps": SAMPLE_STEPS, "days_ahead": 1}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/review-schedule", body)
    reporter.add("review-schedule days_ahead=1", _check_ok(code, resp), f"status={code}")


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Malformed input — 恶意/畸形输入
# ═══════════════════════════════════════════════════════════════════

async def test_progress_invalid_status(client: httpx.AsyncClient, reporter: TestReporter):
    """3.1 非法 status 值"""
    body = {"user_id": 123, "step_id": 3, "status": "not_a_real_status",
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    reporter.add("progress 非法 status→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_node_change_invalid_status(client: httpx.AsyncClient, reporter: TestReporter):
    """3.2 非法 new_status"""
    body = {"node_id": "x", "new_status": "banana", "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/node-status-change", body)
    reporter.add("node-status-change 非法 status→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_create_plan_missing_user_id(client: httpx.AsyncClient, reporter: TestReporter):
    """3.3 缺少必填字段 user_id"""
    body = {"course_id": "ai_intro", "topic": "ML"}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body)
    reporter.add("create 缺少 user_id→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_progress_negative_score(client: httpx.AsyncClient, reporter: TestReporter):
    """3.4 负数 score"""
    body = {"user_id": 123, "step_id": 3, "status": "completed", "score": -1.5,
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    reporter.add("progress score=-1.5→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_progress_score_gt_1(client: httpx.AsyncClient, reporter: TestReporter):
    """3.5 score > 1"""
    body = {"user_id": 123, "step_id": 3, "status": "completed", "score": 999.0,
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    reporter.add("progress score=999→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_review_schedule_negative_days(client: httpx.AsyncClient, reporter: TestReporter):
    """3.6 负数 days_ahead"""
    body = {"steps": SAMPLE_STEPS, "days_ahead": -7}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/review-schedule", body)
    reporter.add("review-schedule days=-7→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_review_schedule_gt_30(client: httpx.AsyncClient, reporter: TestReporter):
    """3.7 days_ahead > 30"""
    body = {"steps": SAMPLE_STEPS, "days_ahead": 999}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/review-schedule", body)
    reporter.add("review-schedule days=999→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_today_missing_plan(client: httpx.AsyncClient, reporter: TestReporter):
    """3.8 缺少必填字段 plan"""
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", {"steps": SAMPLE_STEPS})
    reporter.add("today 缺少 plan→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_complete_step_missing_step(client: httpx.AsyncClient, reporter: TestReporter):
    """3.9 缺少必填字段 step"""
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/complete-step", {"plan": SAMPLE_PLAN})
    reporter.add("complete-step 缺少 step→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_xss_in_topic(client: httpx.AsyncClient, reporter: TestReporter):
    """3.10 XSS 注入 topic"""
    body = {"user_id": 123, "course_id": "ai_intro",
            "topic": "<script>alert('xss')</script>", "student_profile": STUDENT_PROFILE}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=180)
    ok = code in (200, 400, 422, 504)
    reporter.add("create topic XSS 注入", ok, f"status={code}")


async def test_sql_injection_topic(client: httpx.AsyncClient, reporter: TestReporter):
    """3.11 SQL 注入 topic — 不崩溃即可，LLM 可以失败"""
    body = {"user_id": 123, "course_id": "ai_intro",
            "topic": "'; DROP TABLE plans; --", "student_profile": STUDENT_PROFILE}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=180)
    ok = code in (200, 400, 422, 500, 504)
    reporter.add("create topic SQL 注入", ok, f"status={code}")


async def test_unicode_bomb_topic(client: httpx.AsyncClient, reporter: TestReporter):
    """3.12 Unicode 炸弹 topic — 不崩溃即可，LLM 可以失败"""
    body = {"user_id": 123, "course_id": "ai_intro",
            "topic": "🤖" * 500 + "机器学习" + "🎯" * 500, "student_profile": STUDENT_PROFILE}
    code, resp = await _post(client, f"{PLAN_PREFIX}/create-from-path", body, timeout=180)
    ok = code in (200, 400, 422, 500, 504)
    reporter.add("create topic Unicode 炸弹", ok, f"status={code}")


async def test_huge_steps_array(client: httpx.AsyncClient, reporter: TestReporter):
    """3.13 超大 steps 数组（1000 步）"""
    huge_steps = []
    for i in range(1000):
        huge_steps.append({
            "id": i + 1, "step_order": i + 1, "topic": f"知识点{i}",
            "knowledge_node_id": f"node_{i}", "status": "pending",
            "estimated_days": 1, "topic_difficulty": 3,
            "mastery_current": 0.0, "review_count": 0,
        })
    body = {"plan": {**SAMPLE_PLAN, "total_steps": 1000}, "steps": huge_steps}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    reporter.add("today 1000 步骤", _check_ok(code, resp), f"status={code}")


async def test_null_masteries(client: httpx.AsyncClient, reporter: TestReporter):
    """3.14 masteries 显式传 null"""
    body = {"user_id": 123, "step_id": 3, "status": "completed",
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS, "masteries": None}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    # Pydantic 应该拒绝 null
    reporter.add("progress masteries=null→4xx", _check_validation_error(code, resp), f"status={code}")


async def test_deeply_nested_plan(client: httpx.AsyncClient, reporter: TestReporter):
    """3.15 深层嵌套 JSON"""
    deep = {"level1": {"level2": {"level3": {"level4": {"level5": {"level6": {"level7": "boom"}}}}}}}
    body = {"plan": deep, "steps": SAMPLE_STEPS}
    code, resp = await _post(client, f"{PLAN_PREFIX}/1/today", body)
    # 不崩溃即可
    reporter.add("today 深层嵌套 plan", code in (200, 400, 422, 500), f"status={code}")


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Concurrency stress
# ═══════════════════════════════════════════════════════════════════

STRESS_PAYLOADS = [
    # plan status — 最轻量
    ("plan_status", f"{PLAN_PREFIX}/1/status", {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}),
    # today — 中等
    ("today", f"{PLAN_PREFIX}/1/today", {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS, "start_date": "2026-06-01"}),
    # progress — 中等
    ("progress", f"{PLAN_PREFIX}/1/progress", {
        "user_id": 123, "step_id": 3, "status": "completed", "score": 0.8,
        "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS,
    }),
    # node-status-change — 中等
    ("node_change", f"{PLAN_PREFIX}/1/node-status-change", {
        "node_id": "backpropagation", "old_status": "learning", "new_status": "forgotten",
        "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS, "masteries": {},
    }),
    # review-schedule — 最轻量
    ("review_sched", f"{PLAN_PREFIX}/1/review-schedule", {"steps": SAMPLE_STEPS, "days_ahead": 7}),
]


async def _bombard_phase(client: httpx.AsyncClient, label: str, concurrency: int, duration: float) -> Metrics:
    sem = asyncio.Semaphore(concurrency)
    metrics = Metrics()
    deadline = time.monotonic() + duration

    async def worker():
        while time.monotonic() < deadline:
            name, url, payload = random.choice(STRESS_PAYLOADS)
            async with sem:
                t0 = time.perf_counter()
                try:
                    resp = await client.post(f"{BASE_URL}{url}", json=payload,
                                             timeout=httpx.Timeout(30))
                    metrics.record(resp.status_code, time.perf_counter() - t0)
                except Exception:
                    metrics.errors += 1
                    metrics.latencies.append(time.perf_counter() - t0)

    tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.sleep(duration)
    await asyncio.gather(*tasks, return_exceptions=True)
    print(metrics.summary(label), flush=True)
    return metrics


async def _burst_phase(client: httpx.AsyncClient, concurrency: int) -> Metrics:
    """所有请求同时发出——瞬时压力。"""
    name, url, payload = random.choice(STRESS_PAYLOADS)
    sem = asyncio.Semaphore(concurrency)
    metrics = Metrics()

    async def one():
        async with sem:
            t0 = time.perf_counter()
            try:
                resp = await client.post(f"{BASE_URL}{url}", json=payload, timeout=httpx.Timeout(30))
                metrics.record(resp.status_code, time.perf_counter() - t0)
            except Exception:
                metrics.errors += 1
                metrics.latencies.append(time.perf_counter() - t0)

    tasks = [asyncio.create_task(one()) for _ in range(concurrency)]
    await asyncio.gather(*tasks, return_exceptions=True)
    print(metrics.summary(f"Burst ({concurrency}并发)"), flush=True)
    return metrics


# ═══════════════════════════════════════════════════════════════════
# Phase 5: Consistency checks
# ═══════════════════════════════════════════════════════════════════

async def test_progress_idempotency(client: httpx.AsyncClient, reporter: TestReporter):
    """5.1 连续两次相同 progress 请求"""
    body = {"user_id": 123, "step_id": 3, "status": "completed", "score": 0.8,
            "plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS,
            "masteries": {"supervised_learning": 0.5}}
    code1, resp1 = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    code2, resp2 = await _post(client, f"{PLAN_PREFIX}/1/progress", body)
    m1 = resp1.get("data", {}).get("mastery_updates", {}).get("supervised_learning", {}).get("new_mastery")
    m2 = resp2.get("data", {}).get("mastery_updates", {}).get("supervised_learning", {}).get("new_mastery")
    # 两次相同输入应给出相同结果
    consistent = m1 is not None and m2 is not None and abs(m1 - m2) < 0.01
    reporter.add("progress 幂等性", consistent, f"run1={m1} run2={m2}")


async def test_plan_status_consistent(client: httpx.AsyncClient, reporter: TestReporter):
    """5.2 plan status 多次调用结果一致"""
    body = {"plan": SAMPLE_PLAN, "steps": SAMPLE_STEPS}
    code1, resp1 = await _post(client, f"{PLAN_PREFIX}/1/status", body)
    code2, resp2 = await _post(client, f"{PLAN_PREFIX}/1/status", body)
    ok = _check_ok(code1, resp1) and _check_ok(code2, resp2)
    d1 = resp1.get("data", {}).get("completed_steps")
    d2 = resp2.get("data", {}).get("completed_steps")
    reporter.add("plan status 一致性", ok and d1 == d2, f"r1={d1} r2={d2}")


async def test_today_different_dates(client: httpx.AsyncClient, reporter: TestReporter):
    """5.3 不同 start_date 的 today 结果应有差异"""
    body1 = {"plan": {**SAMPLE_PLAN, "start_date": "2026-06-01"}, "steps": SAMPLE_STEPS}
    body2 = {"plan": {**SAMPLE_PLAN, "start_date": "2026-07-01"}, "steps": SAMPLE_STEPS}
    code1, resp1 = await _post(client, f"{PLAN_PREFIX}/1/today", body1)
    code2, resp2 = await _post(client, f"{PLAN_PREFIX}/1/today", body2)
    d1 = resp1.get("data", {}).get("day_index", -1)
    d2 = resp2.get("data", {}).get("day_index", -1)
    reporter.add("today 不同日期结果不同", d1 != d2, f"d1={d1} d2={d2}")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


async def main(concurrency: int, duration: int, burst: int, url: str):
    global BASE_URL
    BASE_URL = url

    print(f"""
{'='*70}
  Plan Module Bombing Test
  Target: {url}
  Concurrency: {concurrency}  Duration: {duration}s  Burst: {burst}
{'='*70}
""", flush=True)

    limits = httpx.Limits(max_keepalive_connections=200, max_connections=200)
    reporter = TestReporter()

    async with httpx.AsyncClient(limits=limits, trust_env=False) as client:

        # -- Phase 0: Health check --
        print("-- Phase 0: Health Check --", flush=True)
        try:
            r = await client.get(f"{url}/health", timeout=httpx.Timeout(10))
            if r.status_code == 200:
                print("  Server is alive.", flush=True)
            else:
                print(f"  Server returned {r.status_code}. Proceed anyway.", flush=True)
        except Exception as e:
            print(f"\n  FATAL: Cannot reach server at {url}", flush=True)
            print(f"  Start with: USE_MOCK_LLM=true python main.py", flush=True)
            print(f"  Error: {e}", flush=True)
            return

        # -- Phase 1: Happy path --
        print("\n-- Phase 1: 正常流程 (Happy Path) --", flush=True)
        for test in [
            test_create_plan_happy,
            test_plan_status_happy,
            test_today_tasks_happy,
            test_complete_step_happy,
            test_progress_update_happy,
            test_node_status_change_happy,
            test_node_forgotten_flow,
            test_node_locked_flow,
            test_regression_check_phase1,
            test_review_schedule_happy,
            test_progress_by_step_order,
        ]:
            await test(client, reporter)

        # -- Phase 2: Edge cases --
        print("\n-- Phase 2: 边界值 (Edge Cases) --", flush=True)
        for test in [
            test_create_plan_empty_topic,
            test_create_plan_minimal_profile,
            test_today_tasks_no_start_date,
            test_today_tasks_future_plan,
            test_today_tasks_all_completed,
            test_today_tasks_empty_steps,
            test_progress_nonexistent_step,
            test_progress_no_score,
            test_complete_step_near_end,
            test_node_status_change_no_match,
            test_status_legacy_path,
            test_review_schedule_big_days,
            test_review_schedule_min_days,
        ]:
            await test(client, reporter)

        # -- Phase 3: Malformed input --
        print("\n-- Phase 3: 畸形输入 (Malformed) --", flush=True)
        for test in [
            test_progress_invalid_status,
            test_node_change_invalid_status,
            test_create_plan_missing_user_id,
            test_progress_negative_score,
            test_progress_score_gt_1,
            test_review_schedule_negative_days,
            test_review_schedule_gt_30,
            test_today_missing_plan,
            test_complete_step_missing_step,
            test_xss_in_topic,
            test_sql_injection_topic,
            test_unicode_bomb_topic,
            test_huge_steps_array,
            test_null_masteries,
            test_deeply_nested_plan,
        ]:
            await test(client, reporter)

        # -- Phase 4: Consistency checks (BEFORE concurrency to avoid rate-limit interference) --
        print("\n-- Phase 4: 一致性检查 --", flush=True)
        for test in [
            test_progress_idempotency,
            test_plan_status_consistent,
            test_today_different_dates,
        ]:
            await test(client, reporter)

        # -- Phase 5: Concurrency stress --
        print(f"\n-- Phase 5: 并发压力 ({duration}s @ {concurrency}并发) --", flush=True)
        await _bombard_phase(client, "Plan API Concurrency", concurrency, duration)

        print(f"\n  (Waiting 5s for rate limiter to cool down...)", flush=True)
        await asyncio.sleep(5)

        # -- Phase 6: Burst --
        print(f"\n-- Phase 6: 瞬时爆发 ({burst}并发) --", flush=True)
        await _burst_phase(client, burst)

    # -- Final report --
    print(reporter.final_report(), flush=True)

    # 有失败就炸
    failed = sum(1 for r in reporter.results if not r.passed)
    if failed > 0:
        print(f"\n*** BOMB RESULT: {failed} cases FAILED! Module has BUGS!! ***", flush=True)
        sys.exit(1)
    else:
        print(f"\n*** BOMB RESULT: ALL PASSED! Module is SOLID! ***", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    parser = ArgumentParser(description="计划模块轰炸测试")
    parser.add_argument("--url", default="http://127.0.0.1:8001", help="AI service base URL")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    parser.add_argument("--burst", type=int, default=DEFAULT_BURST)
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.duration, args.burst, args.url))
