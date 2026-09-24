"""练习域路由：出题 / 解题 / 判分 / 错因 / 评测报告 / 分类 / 会话分析 / 仪表盘 / 画像反哺。"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import (
    CategorizeExerciseRequest,
    DashboardRequest,
    ErrorAnalysisRequest,
    EvaluationReportRequest,
    ExerciseGenRequest,
    GradeRequest,
    ProfileEnrichRequest,
    SessionAnalyzeRequest,
    SolveRequest,
)
from app.utils.prompt_guard import sanitize_model

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/exercise/generate")
async def exercise_generate(body: ExerciseGenRequest):
    body = sanitize_model(body)
    topic = body.topic.strip()
    knowledge_node_id = body.knowledge_node_id
    if not topic and not knowledge_node_id:
        return api.api_error(ErrorCode.INVALID_REQUEST, "topic 和 knowledge_node_id 至少提供一个", status_code=400)

    center = api._get_exercise_center()

    async def event_stream():
        async for event in center.generate_stream(
            topic=topic,
            knowledge_node_id=knowledge_node_id,
            strategy=body.strategy,
            count=body.count,
            difficulty=body.difficulty,
            student_profile=body.student_profile,
        ):
            yield event.to_sse()

    return api.sse_response(event_stream())


@router.post("/solve")
async def solve_question(body: SolveRequest):
    body = sanitize_model(body)
    question = body.question.strip()
    context = body.context
    center = api._get_exercise_center()

    async def event_stream():
        async for event in center.solve_stream(question=question, context=context):
            yield event.to_sse()

    return api.sse_response(event_stream())


@router.post("/exercise/error-analysis")
async def exercise_error_analysis(body: ErrorAnalysisRequest):
    try:
        result = await api._get_exercise_center().analyze_errors(
            errors=body.errors, level=body.level,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Error analysis failed: {e}", exc_info=True)
        return api.api_error(ErrorCode.GENERATION_FAILED, "错题分析失败，请稍后重试", status_code=500)


@router.post("/exercise/grade")
async def grade_exercise(body: GradeRequest):
    if body.type == "choice":
        if body.user_answer is None or body.correct_answer is None:
            return api.api_error(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "user_answer and correct_answer are required",
            )
    elif body.user_answer is None:
        return api.api_error(
            ErrorCode.MISSING_REQUIRED_FIELD, "user_answer is required"
        )

    result = await api._get_exercise_center().grade(
        question_type=body.type,
        user_answer=body.user_answer,
        correct_answer=body.correct_answer,
        choices=body.choices,
        multi=body.multi,
        points=body.points,
        reference_answer=body.reference_answer,
        rubric=body.rubric,
    )
    return api.api_success(result)


@router.post("/evaluation/report")
async def get_evaluation_report(body: EvaluationReportRequest):
    report = await api._get_exercise_center().evaluation_report(
        evaluation_results=body.evaluation_results,
    )
    return api.api_success(report)


@router.post("/exercise/categorize")
async def categorize_exercises(body: CategorizeExerciseRequest):
    """将练习题匹配到知识图谱节点。"""
    exercises = [ex.model_dump() for ex in body.exercises]
    result = await api._get_exercise_center().categorize(
        exercises=exercises,
        knowledge_nodes=body.knowledge_nodes,
        course_id=body.course_id,
    )
    return api.api_success(result)


@router.post("/exercise/session/analyze")
async def analyze_session(body: SessionAnalyzeRequest):
    """分析一次练习会话，返回逐知识点报告 + 掌握度更新建议。"""
    records = [r.model_dump() for r in body.records]
    result = await api._get_exercise_center().analyze_session(
        records=records, masteries=body.masteries, course_id=body.course_id,
    )
    return api.api_success(result)


@router.post("/exercise/dashboard")
async def exercise_dashboard(body: DashboardRequest):
    """练习仪表盘：练习统计 + 薄弱/强项 + 推荐节点。"""
    records = [r.model_dump() for r in body.recent_records]
    result = await api._get_exercise_center().dashboard(
        user_id=body.user_id,
        masteries=body.masteries,
        recent_records=records,
        course_id=body.course_id,
    )
    return api.api_success(result)


@router.post("/exercise/profile/enrich")
async def enrich_profile(body: ProfileEnrichRequest):
    """练习数据反哺学生画像：合并薄弱点、强项、技能等级。"""
    records = [r.model_dump() for r in body.recent_records]
    result = await api._get_exercise_center().enrich_profile(
        user_id=body.user_id,
        student_profile=body.student_profile,
        recent_records=records,
        session_analysis=body.session_analysis,
    )
    return api.api_success(result)
