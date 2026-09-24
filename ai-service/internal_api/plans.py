"""计划域路由：学习路径生成 + 计划步骤 / 进度 / 状态 / 回归 / 复习日程。"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import (
    CompleteStepRequest,
    CreatePlanFromPathRequest,
    NodeStatusChangeRequest,
    PlanStatusRequest,
    ProgressUpdateRequest,
    RegressionCheckRequest,
    ReviewScheduleRequest,
    TodayTasksRequest,
)
from app.centers.plan_center import PlanGenerationError, PlanNotFoundError

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/path/{student_id}")
async def learning_path(student_id: str, body: CreatePlanFromPathRequest):
    workflow = api._get_path_workflow()

    try:
        user_id = int(student_id)
    except (ValueError, TypeError):
        return api.api_error(ErrorCode.INVALID_REQUEST, f"student_id must be an integer, got: {student_id}")

    student_profile = body.student_profile
    topic = body.topic or ""

    try:
        state = await workflow.run({
            "user_id": user_id,
            "student_profile": student_profile,
            "topic": topic,
        })
    except Exception as e:
        logger.error(f"Path workflow failed: {e}", exc_info=True)
        return api.api_error(
            ErrorCode.GENERATION_FAILED, "学习路径生成失败", status_code=500
        )

    return api.api_success({
        "user_id": user_id,
        "steps": state.get("steps", []),
        "concept_graph": state.get("concept_graph", {}),
        "response": state.get("response", ""),
    })


# ── Create Plan From Path ──────────────────────────────────────

@router.post("/plans/create-from-path")
async def create_plan_from_path(body: CreatePlanFromPathRequest):
    """一键生成学习计划。业务编排全部委派给 PlanCenter.create_from_path()。"""
    try:
        result = await api._get_plan_center().create_from_path(
            topic=body.topic or "",
            course_id=body.course_id,
            student_profile=body.student_profile,
        )
        return api.api_success(result)
    except PlanGenerationError as e:
        return api.api_error(ErrorCode.GENERATION_FAILED, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to create plan from path: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "创建学习计划失败，请稍后重试", status_code=500)


# ── Complete Step — 完成学习步骤后触发巩固 ─────────────────────

@router.post("/plans/{plan_id}/complete-step")
async def complete_plan_step(plan_id: int, body: CompleteStepRequest):
    """完成一个学习步骤后调用：生成巩固练习题。

    返回值包含 questions 和 recommended_action，前端据此展示「做两道题巩固」。
    Java 拿到 questions 后存入练习库（带 knowledge_node_id），用户作答后走 exercise 闭环。
    """
    try:
        result = await api._get_plan_center().complete_step(
            step=body.step, plan=body.plan, steps=body.steps,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to complete step: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "生成巩固练习失败", status_code=500)


# ── Today's Tasks — 今日学习任务 + 资源关联 ────────────────────

@router.post("/plans/{plan_id}/today")
async def get_today_tasks(plan_id: int, body: TodayTasksRequest):
    """返回今日应完成的步骤 + 每个步骤的资源建议。"""
    try:
        result = await api._get_plan_center().today_tasks(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            start_date=body.start_date,
            masteries=body.masteries or {},
        )
        return api.api_success(result)
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get today tasks: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "获取今日任务失败", status_code=500)


# ── Progress Update — 更新步骤进度 + 计算掌握度变化 ────────────

@router.post("/plans/{plan_id}/progress")
async def update_plan_progress(plan_id: int, body: ProgressUpdateRequest):
    """Java 在用户完成步骤学习/练习后调用，返回掌握度变化与更新后的步骤列表。"""
    try:
        result = await api._get_plan_center().update_progress(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            masteries=body.masteries or {},
            step_id=body.step_id,
            step_order=body.step_order,
            status=body.status,
            score=body.score,
            activity_type=body.activity_type,
            duration_minutes=body.duration_minutes,
        )
        return api.api_success(result)
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "更新进度失败", status_code=500)


# ── Node Status Change — 图谱节点状态变化 → 计划联动 ───────────

@router.post("/plans/{plan_id}/node-status-change")
async def on_node_status_change(plan_id: int, body: NodeStatusChangeRequest):
    """图谱节点状态变化时同步计划，返回步骤联动建议。

    场景：
    - 节点被掌握（mastered）→ 计划中对应步骤可标记为 completed
    - 节点被遗忘（forgotten）→ 计划中对应步骤需重新安排复习
    - 节点被解锁（learning）→ 计划中对应步骤可从 locked 变为 pending
    """
    try:
        result = await api._get_plan_center().node_status_change(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            masteries=body.masteries or {},
            node_id=body.node_id,
            old_status=body.old_status,
            new_status=body.new_status,
        )
        return api.api_success(result)
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to handle node status change: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "节点状态联动失败", status_code=500)


# ── Plan Status ────────────────────────────────────────────────

@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    """查询计划状态（含软着陆触发检测）。Java 传入 plan + steps 数据。"""
    try:
        return api.api_success(await api._get_plan_center().plan_status(
            plan=body.plan, steps=body.steps,
        ))
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get plan status: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "查询计划状态失败", status_code=500)


@router.post("/plans/status")
async def get_plan_status_legacy(body: PlanStatusRequest):
    """兼容旧路径：/internal/plans/status（无 path 参数 plan_id）。

    路径不携带 plan_id，响应中的 plan_id 取 body.plan.id。
    """
    try:
        return api.api_success(await api._get_plan_center().plan_status(
            plan=body.plan, steps=body.steps,
        ))
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get plan status: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "查询计划状态失败", status_code=500)


# ── Regression Check ───────────────────────────────────────────

@router.post("/plans/{plan_id}/regression-check")
async def regression_check(plan_id: int, body: RegressionCheckRequest):
    """回归检测管线：出题 → 判分 → 重排。纯算法，不写 DB。"""
    try:
        result = await api._get_plan_center().regression_check(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            days_idle=body.days_idle,
            answers=body.answers,
        )
        return api.api_success(result)
    except PlanNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed regression check: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "回归检测失败，请稍后重试", status_code=500)


# ── Review Schedule ────────────────────────────────────────────

@router.post("/plans/{plan_id}/review-schedule")
async def get_review_schedule(plan_id: int, body: ReviewScheduleRequest):
    """获取未来 N 天的复习日程。Java 传入 steps 数据。"""
    try:
        result = await api._get_plan_center().review_schedule(
            plan_id=plan_id, steps=body.steps, days_ahead=body.days_ahead,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to get review schedule: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "获取复习日程失败", status_code=500)
