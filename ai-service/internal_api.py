"""
Internal API — Architecture #2: Java → Python 纯 AI 推理

原则：
- Java 把所有需要的数据放在请求体中传给 Python
- Python 只做 AI 计算，返回结果
- Python 不调 Java API，不持久化
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse

from app.utils.sse_heartbeat import sse_heartbeat_generator
from app.utils.prompt_guard import sanitize_model
from app.api.errors import ErrorCode, api_error, api_success
from app.api.models import (
    ProfileChatRequest,
    ProfileWorkflowStatusRequest,
    ResourceGenRequest,
    ExportPptxRequest,
    ExportDocxRequest,
    ExportPdfRequest,
    TutorChatRequest,
    ExerciseGenRequest,
    GradeRequest,
    EvaluationReportRequest,
    SolveRequest,
    ErrorAnalysisRequest,
    UnifiedChatRequest,
    RegressionCheckRequest,
    CreatePlanFromPathRequest,
    InquiryResolveRequest,
    KnowledgeGraphRequest,
    KnowledgeGraphNodeRequest,
    GraphExtractRequest,
    GraphNodesRequest,
    MasteryUpdateRequest,
    GraphReloadRequest,
    GraphProgressRequest,
    GraphPrerequisiteRequest,
    NodeDeleteRequest,
    NodeUpdateRequest,
    GraphSuggestEdgesRequest,
    GraphMermaidRequest,
    GraphLayeredRequest,
    PlanStatusRequest,
    ReviewScheduleRequest,
    SummaryRequest,
    CategorizeExerciseRequest,
    SessionAnalyzeRequest,
    DashboardRequest,
    ProfileEnrichRequest,
    CompleteStepRequest,
    TodayTasksRequest,
    ProgressUpdateRequest,
    NodeStatusChangeRequest,
    ResourceLinkRequest,
)
from app.services.plan_service import get_plan_service
from app.services.knowledge_extraction import extract_knowledge_nodes
from app.services.plan_constants import RETURN_MESSAGES
from app.services.intent_extractor import IntentExtractor
from app.centers.chat_center import ChatCenter
from app.centers.plan_center import PlanCenter, PlanGenerationError, PlanNotFoundError
from app.centers.resource_center import ResourceCenter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal")

_chat_center_singleton = None
_chat_center_lock = threading.Lock()

_profile_agent_singleton = None
_tutor_agent_singleton = None
_content_agent_singleton = None
_exercise_agent_singleton = None
_exercise_center_singleton = None
_exercise_center_lock = threading.Lock()
_path_agent_singleton = None
_mindmap_agent_singleton = None
_code_agent_singleton = None
_profile_workflow_singleton = None
_resource_center_singleton = None
_resource_center_lock = threading.Lock()
_path_workflow_singleton = None
_inquiry_service_singleton = None
_tutor_center_singleton = None
_tutor_center_lock = threading.Lock()


def _get_chat_center():
    global _chat_center_singleton
    if _chat_center_singleton is None:
        with _chat_center_lock:
            if _chat_center_singleton is None:
                _chat_center_singleton = ChatCenter()
    return _chat_center_singleton


def _get_mock_flag() -> bool:
    return False


def _get_profile_agent():
    global _profile_agent_singleton
    if _profile_agent_singleton is None:
        from app.agents.profile_agent import ProfileAgent
        _profile_agent_singleton = ProfileAgent(use_mock_llm=_get_mock_flag())
    return _profile_agent_singleton


def _get_tutor_agent():
    global _tutor_agent_singleton
    if _tutor_agent_singleton is None:
        from app.agents.tutor_agent import TutorAgent
        _tutor_agent_singleton = TutorAgent(use_mock_llm=_get_mock_flag())
    return _tutor_agent_singleton


def _get_tutor_center():
    """惰性单例工厂：答疑域唯一业务入口装配点。

    注入 API 层既有的 TutorAgent / ProfileAgent 单例，与收口前 /tutor/chat
    的构造一致；测试 patch 目标为 internal_api._get_tutor_center。
    """
    global _tutor_center_singleton
    if _tutor_center_singleton is None:
        with _tutor_center_lock:
            if _tutor_center_singleton is None:
                from app.centers.tutor_center import TutorCenter
                _tutor_center_singleton = TutorCenter(
                    tutor_agent=_get_tutor_agent(),
                    profile_agent=_get_profile_agent(),
                )
    return _tutor_center_singleton


def _get_content_agent():
    global _content_agent_singleton
    if _content_agent_singleton is None:
        from app.agents.content_agent import ContentAgent
        _content_agent_singleton = ContentAgent(use_mock_llm=_get_mock_flag())
    return _content_agent_singleton


def _get_exercise_agent():
    global _exercise_agent_singleton
    if _exercise_agent_singleton is None:
        from app.agents.exercise_agent import ExerciseAgent
        _exercise_agent_singleton = ExerciseAgent(use_mock_llm=_get_mock_flag())
    return _exercise_agent_singleton


def _get_exercise_center():
    """惰性单例工厂：练习域唯一业务入口装配点。

    装配的 ExerciseAgent 不带 model_profile，与收口前 /exercise/generate 与
    complete-step 的构造一致；聊天侧 ExerciseCenter.execute() 的惰性默认
    （PROFILE_EXERCISE）不受影响。
    """
    global _exercise_center_singleton
    if _exercise_center_singleton is None:
        with _exercise_center_lock:
            if _exercise_center_singleton is None:
                from app.agents.solve_agent import SolveAgent
                from app.centers.exercise_center import ExerciseCenter
                _exercise_center_singleton = ExerciseCenter(
                    exercise_agent=_get_exercise_agent(),
                    solve_agent=SolveAgent(use_mock_llm=_get_mock_flag()),
                )
    return _exercise_center_singleton


def _get_path_agent():
    global _path_agent_singleton
    if _path_agent_singleton is None:
        from app.agents.path_agent import PathAgent
        _path_agent_singleton = PathAgent(use_mock_llm=_get_mock_flag())
    return _path_agent_singleton


def _get_mindmap_agent():
    global _mindmap_agent_singleton
    if _mindmap_agent_singleton is None:
        from app.agents.mindmap_agent import MindMapAgent
        _mindmap_agent_singleton = MindMapAgent(use_mock_llm=_get_mock_flag())
    return _mindmap_agent_singleton


_plan_center_singleton = None
_plan_center_lock = threading.Lock()


def _get_code_agent():
    global _code_agent_singleton
    if _code_agent_singleton is None:
        from app.agents.code_agent import CodeAgent
        _code_agent_singleton = CodeAgent(use_mock_llm=_get_mock_flag())
    return _code_agent_singleton


def _get_profile_workflow():
    global _profile_workflow_singleton
    if _profile_workflow_singleton is None:
        from app.workflows.profile_workflow import ProfileWorkflow
        _profile_workflow_singleton = ProfileWorkflow(use_mock=_get_mock_flag())
    return _profile_workflow_singleton


def _get_resource_center() -> ResourceCenter:
    """资源域唯一业务入口工厂（API 层唯一允许装配 ResourceGenWorkflow 的位置）。

    返回单例 ResourceCenter(resource_workflow=ResourceGenWorkflow(use_mock=_get_mock_flag()))。
    API 路由不再直接获取 ResourceGenWorkflow；测试 patch 目标为 internal_api._get_resource_center。
    """
    global _resource_center_singleton
    if _resource_center_singleton is None:
        with _resource_center_lock:
            if _resource_center_singleton is None:
                from app.workflows.resource_gen import ResourceGenWorkflow
                _resource_center_singleton = ResourceCenter(
                    resource_workflow=ResourceGenWorkflow(use_mock=_get_mock_flag()),
                )
    return _resource_center_singleton


def _get_path_workflow():
    global _path_workflow_singleton
    if _path_workflow_singleton is None:
        from app.workflows.learning_path import LearningPathWorkflow
        _path_workflow_singleton = LearningPathWorkflow(use_mock=_get_mock_flag())
    return _path_workflow_singleton


def _get_inquiry_service():
    global _inquiry_service_singleton
    if _inquiry_service_singleton is None:
        from app.services.inquiry_service import InquiryService
        _inquiry_service_singleton = InquiryService()
    return _inquiry_service_singleton


def _get_plan_center():
    """惰性单例工厂：构造 PlanCenter 并装配 Goal/Decompose/Schedule Agent。

    该工厂是 API 层与 PlanCenter 之间的唯一依赖装配点。
    graph_service / step_classifier 留 None，由 PlanCenter 走现网 fallback。
    """
    global _plan_center_singleton
    if _plan_center_singleton is None:
        with _plan_center_lock:
            if _plan_center_singleton is None:
                from app.agents.goal_agent import GoalAgent
                from app.agents.decompose_agent import DecomposeAgent
                from app.agents.schedule_agent import ScheduleAgent
                from app.centers.plan_center import PlanCenter

                mock = _get_mock_flag()
                _plan_center_singleton = PlanCenter(
                    goal_agent=GoalAgent(use_mock_llm=mock),
                    decompose_agent=DecomposeAgent(use_mock_llm=mock),
                    schedule_agent=ScheduleAgent(use_mock_llm=mock),
                )
    return _plan_center_singleton


# ── SSE 输出安全 ─────────────────────────────────────────────────

def _sse_sanitize(text: str) -> str:
    """移除用户文本中的 SSE 控制序列，防止注入攻击。"""
    return text.replace("\n\n", "  ").replace("\ndata:", " data:").replace("\r", "")


def _sse_stream_chunks(text: str, size: int = 4):
    """将文本按固定大小切分为块生成器，用于 SSE token 流。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


# ── 多模态消息构建 ──────────────────────────────────────────────

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _extract_text_from_multimodal(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(parts)
    return ""


_SSRF_BLOCKED_NETWORKS = re.compile(
    r"://(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"0\.0\.0\.0|169\.254\.\d+\.\d+|\[::1\]|\[fe80:)",
    re.IGNORECASE,
)

_SSRF_DECIMAL_IP = re.compile(r"://(\d{8,10})(?:/|$|:)", re.IGNORECASE)
_SSRF_HEX_IP = re.compile(r"://0x[0-9a-f]{6,8}(?:/|$|:)", re.IGNORECASE)
_SSRF_OCTAL_IP = re.compile(r"://0[0-7]{9,11}(?:/|$|:)", re.IGNORECASE)


def _is_internal_url(url: str) -> bool:
    if _SSRF_BLOCKED_NETWORKS.search(url):
        return True
    dec_match = _SSRF_DECIMAL_IP.search(url)
    if dec_match:
        try:
            ip_int = int(dec_match.group(1))
            octets = [(ip_int >> 24) & 0xFF, (ip_int >> 16) & 0xFF, (ip_int >> 8) & 0xFF, ip_int & 0xFF]
            ip_str = ".".join(str(o) for o in octets)
            if _SSRF_BLOCKED_NETWORKS.search(f"://{ip_str}"):
                return True
        except (ValueError, OverflowError):
            pass
    if _SSRF_HEX_IP.search(url) or _SSRF_OCTAL_IP.search(url):
        return True
    return False


def _build_multimodal_message(text: str, images: list[str] | None) -> dict:
    if not images:
        return {"role": "user", "content": text}

    content_parts: list[dict] = []
    if text:
        content_parts.append({"type": "text", "text": text})

    for img in images:
        if not img or not img.strip():
            continue
        if img.startswith("data:image/"):
            mime_end = img.find(";")
            if mime_end > 0:
                mime = img[len("data:"):mime_end]
                if mime not in ALLOWED_IMAGE_MIMES:
                    logger.warning(f"Rejected image with unsupported MIME: {mime}")
                    continue
            url = img
        elif img.startswith("http://") or img.startswith("https://"):
            if _is_internal_url(img):
                logger.warning(f"Rejected internal/infra URL for SSRF prevention: {img[:80]}")
                continue
            url = img
        else:
            url = f"data:image/jpeg;base64,{img}"
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    if not content_parts:
        return {"role": "user", "content": text}
    if len(content_parts) == 1 and content_parts[0].get("type") == "text":
        return {"role": "user", "content": text}
    return {"role": "user", "content": content_parts}


# ═══════════════════════════════════════════════════════════════════
# Profile Chat
# ═══════════════════════════════════════════════════════════════════

@router.post("/profile/chat")
async def profile_chat(body: ProfileChatRequest):
    body = sanitize_model(body)
    messages = body.messages
    current_profile = body.student_profile

    workflow = _get_profile_workflow()

    async def event_stream():
        try:
            state = await workflow.run({
                "messages": messages,
                "user_id": body.user_id,
                "current_profile": current_profile,
            })

            response = state.get("response", "")
            if response:
                for chunk in _sse_stream_chunks(response):
                    await asyncio.sleep(0.04)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            if state.get("profile_changed"):
                yield f"data: {json.dumps({'type': 'profile_update', 'content': state.get('current_profile', {})}, ensure_ascii=False)}\n\n"

            if state.get("profile_complete"):
                yield f"data: {json.dumps({'type': 'profile_complete', 'filled_dimensions': state.get('filled_dimensions', 0)}, ensure_ascii=False)}\n\n"

            done_payload = {"type": "done"}
            if state.get("profile_changed"):
                done_payload["profile_delta"] = state.get("current_profile", {})
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Profile chat SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '画像对话失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Resources Generate
# ═══════════════════════════════════════════════════════════════════

@router.post("/resources/generate")
async def resources_generate(body: ResourceGenRequest):
    body = sanitize_model(body)
    topic = body.topic.strip()
    if not topic:
        return api_error(ErrorCode.INVALID_REQUEST, "topic 不能为空白", status_code=400)
    student_profile = body.student_profile
    resource_type = body.resource_type

    async def event_stream():
        async for event in _get_resource_center().stream_generate(
            user_id=body.user_id,
            topic=topic,
            student_profile=student_profile,
            resource_type=resource_type or "",
        ):
            yield event.to_sse()

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Tutor Chat
# ═══════════════════════════════════════════════════════════════════

@router.post("/tutor/chat")
async def tutor_chat(body: TutorChatRequest):
    body = sanitize_model(body)
    messages = body.messages
    student_profile = body.student_profile

    async def event_stream():
        async for event in _get_tutor_center().stream_chat(
            messages=messages,
            student_profile=student_profile,
        ):
            yield event.to_sse()

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Exercise Generate
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/generate")
async def exercise_generate(body: ExerciseGenRequest):
    body = sanitize_model(body)
    topic = body.topic.strip()
    knowledge_node_id = body.knowledge_node_id
    if not topic and not knowledge_node_id:
        return api_error(ErrorCode.INVALID_REQUEST, "topic 和 knowledge_node_id 至少提供一个", status_code=400)

    center = _get_exercise_center()

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

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Learning Path (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/path/{student_id}")
async def learning_path(student_id: str, body: CreatePlanFromPathRequest):
    workflow = _get_path_workflow()

    try:
        user_id = int(student_id)
    except (ValueError, TypeError):
        return api_error(ErrorCode.INVALID_REQUEST, f"student_id must be an integer, got: {student_id}")

    student_profile = body.student_profile
    topic = body.topic or ""

    try:
        state = await workflow.run({
            "user_id": user_id,
            "student_profile": student_profile,
            "topic": topic,
        })
    except Exception as e:
        logger.error(f"Path workflow failed: {e}")
        return api_error(
            ErrorCode.GENERATION_FAILED, "学习路径生成失败", status_code=500
        )

    return api_success({
        "user_id": user_id,
        "steps": state.get("steps", []),
        "concept_graph": state.get("concept_graph", {}),
        "response": state.get("response", ""),
    })


# ═══════════════════════════════════════════════════════════════════
# Profile Workflow Status (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/profile/workflow/status")
async def profile_workflow_status(body: ProfileWorkflowStatusRequest):
    workflow = _get_profile_workflow()
    status = workflow.check_profile_status(body.student_profile)
    return api_success(status)


# ═══════════════════════════════════════════════════════════════════
# PPTX Export / Download
# ═══════════════════════════════════════════════════════════════════

@router.post("/resources/export-pptx")
async def export_pptx(body: ExportPptxRequest):
    from app.utils.ppt_exporter import export_to_pptx

    content_blocks = body.content_blocks
    title = body.title
    output_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.pptx")

    try:
        result_path = export_to_pptx(content_blocks, output_path, title)
    except Exception as e:
        logger.error(f"PPTX export failed: {e}")
        return api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api_success({"filename": os.path.basename(result_path)})


_EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "exports")
_ALLOWED_EXTENSIONS = frozenset({".pptx", ".pdf", ".docx"})


@router.get("/resources/download-pptx")
async def download_pptx(filename: str = Query(...)):
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ".pptx":
        return api_error(ErrorCode.INVALID_REQUEST, "不支持的文件类型", status_code=400)
    file_path = os.path.join(_EXPORTS_DIR, safe_name)
    if not os.path.realpath(file_path).startswith(os.path.realpath(_EXPORTS_DIR)):
        return api_error(ErrorCode.INVALID_REQUEST, "非法文件路径", status_code=400)
    if not os.path.exists(file_path):
        return api_error(ErrorCode.NOT_FOUND, "文件不存在或已过期", status_code=404)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=safe_name,
    )


# ── DOCX Export / Download ────────────────────────────────────

@router.post("/resources/export-docx")
async def export_docx(body: ExportDocxRequest):
    from app.utils.docx_exporter import export_to_docx

    content_blocks = body.content_blocks
    title = body.title
    sub_type = body.sub_type
    output_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.docx")

    try:
        result_path = export_to_docx(content_blocks, output_path, title, sub_type)
    except Exception as e:
        logger.error(f"DOCX export failed: {e}")
        return api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api_success({"filename": os.path.basename(result_path)})


@router.get("/resources/download-docx")
async def download_docx(filename: str = Query(...)):
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ".docx":
        return api_error(ErrorCode.INVALID_REQUEST, "不支持的文件类型", status_code=400)
    file_path = os.path.join(_EXPORTS_DIR, safe_name)
    if not os.path.realpath(file_path).startswith(os.path.realpath(_EXPORTS_DIR)):
        return api_error(ErrorCode.INVALID_REQUEST, "非法文件路径", status_code=400)
    if not os.path.exists(file_path):
        return api_error(ErrorCode.NOT_FOUND, "文件不存在或已过期", status_code=404)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )


# ── PDF Export / Download ──────────────────────────────────────

@router.post("/resources/export-pdf")
async def export_pdf(body: ExportPdfRequest):
    from app.utils.pdf_exporter import export_to_pdf

    content_blocks = body.content_blocks
    title = body.title
    output_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.pdf")

    try:
        result_path = export_to_pdf(content_blocks, output_path, title)
    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        return api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api_success({"filename": os.path.basename(result_path)})


@router.get("/resources/download-pdf")
async def download_pdf(filename: str = Query(...)):
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ".pdf":
        return api_error(ErrorCode.INVALID_REQUEST, "不支持的文件类型", status_code=400)
    file_path = os.path.join(_EXPORTS_DIR, safe_name)
    if not os.path.realpath(file_path).startswith(os.path.realpath(_EXPORTS_DIR)):
        return api_error(ErrorCode.INVALID_REQUEST, "非法文件路径", status_code=400)
    if not os.path.exists(file_path):
        return api_error(ErrorCode.NOT_FOUND, "文件不存在或已过期", status_code=404)
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=safe_name,
    )


# ═══════════════════════════════════════════════════════════════════
# Solve
# ═══════════════════════════════════════════════════════════════════

@router.post("/solve")
async def solve_question(body: SolveRequest):
    body = sanitize_model(body)
    question = body.question.strip()
    context = body.context
    center = _get_exercise_center()

    async def event_stream():
        async for event in center.solve_stream(question=question, context=context):
            yield event.to_sse()

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Exercise Error Analysis
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/error-analysis")
async def exercise_error_analysis(body: ErrorAnalysisRequest):
    try:
        result = await _get_exercise_center().analyze_errors(
            errors=body.errors, level=body.level,
        )
        return api_success(result)
    except Exception as e:
        logger.error(f"Error analysis failed: {e}")
        return api_error(ErrorCode.GENERATION_FAILED, "错题分析失败，请稍后重试", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Grade Exercise
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/grade")
async def grade_exercise(body: GradeRequest):
    if body.type == "choice":
        if body.user_answer is None or body.correct_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "user_answer and correct_answer are required",
            )
    elif body.user_answer is None:
        return api_error(
            ErrorCode.MISSING_REQUIRED_FIELD, "user_answer is required"
        )

    result = await _get_exercise_center().grade(
        question_type=body.type,
        user_answer=body.user_answer,
        correct_answer=body.correct_answer,
        choices=body.choices,
        multi=body.multi,
        points=body.points,
        reference_answer=body.reference_answer,
        rubric=body.rubric,
    )
    return api_success(result)


# ═══════════════════════════════════════════════════════════════════
# Evaluation Report
# ═══════════════════════════════════════════════════════════════════

@router.post("/evaluation/report")
async def get_evaluation_report(body: EvaluationReportRequest):
    report = await _get_exercise_center().evaluation_report(
        evaluation_results=body.evaluation_results,
    )
    return api_success(report)


# ═══════════════════════════════════════════════════════════════════
# Exercise Categorize
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/categorize")
async def categorize_exercises(body: CategorizeExerciseRequest):
    """将练习题匹配到知识图谱节点。"""
    exercises = [ex.model_dump() for ex in body.exercises]
    result = await _get_exercise_center().categorize(
        exercises=exercises,
        knowledge_nodes=body.knowledge_nodes,
        course_id=body.course_id,
    )
    return api_success(result)


# ═══════════════════════════════════════════════════════════════════
# Exercise Session Analytics
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/session/analyze")
async def analyze_session(body: SessionAnalyzeRequest):
    """分析一次练习会话，返回逐知识点报告 + 掌握度更新建议。"""
    records = [r.model_dump() for r in body.records]
    result = await _get_exercise_center().analyze_session(
        records=records, masteries=body.masteries, course_id=body.course_id,
    )
    return api_success(result)


@router.post("/exercise/dashboard")
async def exercise_dashboard(body: DashboardRequest):
    """练习仪表盘：练习统计 + 薄弱/强项 + 推荐节点。"""
    records = [r.model_dump() for r in body.recent_records]
    result = await _get_exercise_center().dashboard(
        user_id=body.user_id,
        masteries=body.masteries,
        recent_records=records,
        course_id=body.course_id,
    )
    return api_success(result)


@router.post("/exercise/profile/enrich")
async def enrich_profile(body: ProfileEnrichRequest):
    """练习数据反哺学生画像：合并薄弱点、强项、技能等级。"""
    records = [r.model_dump() for r in body.recent_records]
    result = await _get_exercise_center().enrich_profile(
        user_id=body.user_id,
        student_profile=body.student_profile,
        recent_records=records,
        session_analysis=body.session_analysis,
    )
    return api_success(result)


# ═══════════════════════════════════════════════════════════════════
# Knowledge Graph (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

_graph_service_singleton = None


def _get_graph_service():
    global _graph_service_singleton
    if _graph_service_singleton is None:
        from app.services.graph_service import get_graph_service
        _graph_service_singleton = get_graph_service()
    return _graph_service_singleton


@router.post("/knowledge-graph/{course_id}")
async def get_knowledge_graph(course_id: str, body: KnowledgeGraphRequest):
    try:
        graph_service = _get_graph_service()
        graph = await graph_service.get_graph(
            course_id=course_id, masteries=body.masteries
        )
        return api_success(graph)
    except Exception as e:
        logger.error(f"Failed to get knowledge graph: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "获取知识图谱失败", status_code=500)


@router.post("/knowledge-graph/{course_id}/node/{node_id}")
async def get_node_card(course_id: str, node_id: str, body: KnowledgeGraphNodeRequest):
    try:
        graph_service = _get_graph_service()
        card = await graph_service.get_node_card(
            node_id=node_id,
            course_id=course_id,
            masteries=body.masteries,
            total_exercises=body.total_exercises,
            last_practiced=body.last_practiced,
        )
        return api_success(card)
    except ValueError:
        return api_error(ErrorCode.NOT_FOUND, "节点不存在", status_code=404)
    except Exception as e:
        logger.error(f"Failed to get node card: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "获取节点卡片失败", status_code=500)


@router.post("/graph/extract")
async def graph_extract(body: GraphExtractRequest):
    try:
        groups = await extract_knowledge_nodes(
            course_id=body.course_id,
            user_message=body.user_message,
            assistant_reply=body.assistant_reply,
            existing_node_ids=body.existing_node_ids,
        )
        return api_success({
            "primary": groups.get("primary", []),
            "related": groups.get("related", []),
            "broad": groups.get("broad", []),
            "candidates": groups.get("all", []),
        })
    except Exception as e:
        logger.error(f"Failed to extract knowledge nodes: {e}")
        return api_error(ErrorCode.GENERATION_FAILED, "知识节点提取失败", status_code=500)


@router.post("/graph/nodes")
async def graph_nodes(body: GraphNodesRequest):
    try:
        graph_service = _get_graph_service()
        for update in body.updates:
            if update.action == "add_node":
                graph_service.add_node(body.course_id, update.data)
            elif update.action == "add_edge":
                graph_service.add_edge(body.course_id, update.data)
        graph = await graph_service.get_graph(course_id=body.course_id)
        return api_success(graph)
    except ValueError as e:
        return api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to apply graph updates: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "图谱更新失败", status_code=500)


@router.post("/graph/masteries")
async def update_masteries(body: MasteryUpdateRequest):
    """根据学习事件批量更新节点掌握度。Python 只计算，Java 自行持久化结果。"""
    if not body.events:
        return api_error(ErrorCode.INVALID_REQUEST, "events 不能为空", status_code=400)

    plan_service = get_plan_service()
    result = dict(body.masteries)

    for event in body.events:
        node_id = event.node_id
        current = result.get(node_id, 0.0)
        new_mastery = plan_service.update_mastery(current, event.event_type, event.score)
        result[node_id] = new_mastery

    return api_success({"masteries": result})


@router.post("/graph/reload")
async def reload_graph(body: GraphReloadRequest):
    """热更新知识图谱骨架（管理员触发）。"""
    from app.services.graph_service import get_graph_service
    graph_service = get_graph_service()
    try:
        graph = graph_service.load_skeleton(force_reload=True)
        return api_success({
            "status": "reloaded",
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
        })
    except Exception as e:
        logger.error(f"Failed to reload graph skeleton: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "图谱热更新失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Graph Phase A: 图谱分析
# ═══════════════════════════════════════════════════════════════════


@router.post("/graph/next-node")
async def recommend_next_node(body: GraphProgressRequest):
    """知识缺口分析：根据当前掌握度推荐下一个该学的节点。"""
    try:
        graph_service = _get_graph_service()
        candidates = graph_service.recommend_next_node(body.masteries, body.course_id)
        return api_success({"recommended": candidates})
    except Exception as e:
        logger.error(f"Failed to recommend next node: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "节点推荐失败", status_code=500)


@router.post("/graph/progress")
async def get_progress_summary(body: GraphProgressRequest):
    """学习进度概要：全局掌握率 + 各分类统计。"""
    try:
        graph_service = _get_graph_service()
        summary = graph_service.get_progress_summary(body.masteries, body.course_id)
        return api_success(summary)
    except Exception as e:
        logger.error(f"Failed to get progress summary: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "进度概要获取失败", status_code=500)


@router.post("/graph/check-prerequisites")
async def check_prerequisites(body: GraphPrerequisiteRequest):
    """前置条件检查：用户是否可以学习指定节点。"""
    try:
        graph_service = _get_graph_service()
        result = graph_service.check_prerequisites(
            body.node_id, body.masteries, body.threshold, body.course_id
        )
        return api_success(result)
    except Exception as e:
        logger.error(f"Failed to check prerequisites: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "前置条件检查失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Graph Phase B: 图谱维护
# ═══════════════════════════════════════════════════════════════════


@router.post("/graph/nodes/{node_id}/delete")
async def delete_node(node_id: str, body: NodeDeleteRequest):
    """删除动态节点（骨架节点不可删）。"""
    try:
        graph_service = _get_graph_service()
        deleted = graph_service.delete_node(body.course_id, node_id)
        return api_success({"deleted": deleted, "node_id": node_id})
    except ValueError as e:
        return api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to delete node: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "节点删除失败", status_code=500)


@router.post("/graph/nodes/{node_id}/update")
async def update_node(node_id: str, body: NodeUpdateRequest):
    """更新节点元数据。骨架节点仅可改 difficulty/category，动态节点全字段可改。"""
    try:
        graph_service = _get_graph_service()
        updated = graph_service.update_node(body.course_id, node_id, body.updates)
        return api_success({"node": updated})
    except ValueError as e:
        return api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to update node: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "节点更新失败", status_code=500)


@router.post("/graph/suggest-edges")
async def suggest_edges(body: GraphSuggestEdgesRequest):
    """LLM 自动补边：分析未连通节点对，建议遗漏的图谱关系。"""
    try:
        graph_service = _get_graph_service()
        suggestions = await graph_service.suggest_edges(body.course_id)
        return api_success({"suggestions": suggestions})
    except Exception as e:
        logger.error(f"Failed to suggest edges: {e}")
        return api_error(ErrorCode.GENERATION_FAILED, "补边建议生成失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Graph Phase C: 可视化
# ═══════════════════════════════════════════════════════════════════


@router.post("/graph/export-mermaid")
async def export_mermaid(body: GraphMermaidRequest):
    """导出知识图谱为 Mermaid 流程图语法。"""
    try:
        graph_service = _get_graph_service()
        mermaid = graph_service.export_mermaid(body.course_id, body.masteries)
        return api_success({"mermaid": mermaid})
    except Exception as e:
        logger.error(f"Failed to export mermaid: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "Mermaid 导出失败", status_code=500)


@router.post("/graph/layered")
async def get_layered_graph(body: GraphLayeredRequest):
    """返回带层级信息的图谱（前端分层布局）。"""
    try:
        graph_service = _get_graph_service()
        graph = graph_service.get_layered_graph(body.masteries, body.course_id)
        return api_success(graph)
    except Exception as e:
        logger.error(f"Failed to get layered graph: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "分层图谱获取失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Create Plan From Path
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/create-from-path")
async def create_plan_from_path(body: CreatePlanFromPathRequest):
    """一键生成学习计划。业务编排全部委派给 PlanCenter.create_from_path()。"""
    try:
        result = await _get_plan_center().create_from_path(
            topic=body.topic or "",
            course_id=body.course_id,
            student_profile=body.student_profile,
        )
        return api_success(result)
    except PlanGenerationError as e:
        return api_error(ErrorCode.GENERATION_FAILED, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to create plan from path: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "创建学习计划失败，请稍后重试", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Complete Step — 完成学习步骤后触发巩固
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/complete-step")
async def complete_plan_step(plan_id: int, body: CompleteStepRequest):
    """完成一个学习步骤后调用：生成巩固练习题。

    返回值包含 questions 和 recommended_action，前端据此展示「做两道题巩固」。
    Java 拿到 questions 后存入练习库（带 knowledge_node_id），用户作答后走 exercise 闭环。
    """
    try:
        step = body.step
        step_topic = step.get("topic", "")
        knowledge_node_id = step.get("knowledge_node_id", "")
        plan = body.plan
        all_steps = body.steps

        # 判断是否最后一两步 → 生成综合性复习题
        completed = plan.get("completed_steps", 0)
        total = plan.get("total_steps", len(all_steps))
        is_near_end = total > 0 and (completed / total) >= 0.8

        generated = await _get_exercise_center().generate_consolidation(
            topic=step_topic,
            knowledge_node_id=knowledge_node_id,
            is_near_end=is_near_end,
        )
        questions = generated.get("questions", [])

        return api_success({
            "step_order": step.get("step_order"),
            "step_completed": True,
            "recommended_action": "comprehensive_review" if is_near_end else "consolidation",
            "questions": questions,
            "message": (
                "你已经接近计划尾声，来做几道综合题检验整体掌握情况！"
                if is_near_end
                else f"完成「{step_topic}」的学习，来做 {len(questions)} 道题巩固一下吧"
            ),
        })
    except Exception as e:
        logger.error(f"Failed to complete step: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "生成巩固练习失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Today's Tasks — 今日学习任务 + 资源关联
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/today")
async def get_today_tasks(plan_id: int, body: TodayTasksRequest):
    """返回今日应完成的步骤 + 每个步骤的资源建议。"""
    try:
        result = await _get_plan_center().today_tasks(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            start_date=body.start_date,
            masteries=body.masteries or {},
        )
        return api_success(result)
    except PlanNotFoundError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get today tasks: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "获取今日任务失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Progress Update — 更新步骤进度 + 计算掌握度变化
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/progress")
async def update_plan_progress(plan_id: int, body: ProgressUpdateRequest):
    """Java 在用户完成步骤学习/练习后调用，返回掌握度变化与更新后的步骤列表。"""
    try:
        result = await _get_plan_center().update_progress(
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
        return api_success(result)
    except PlanNotFoundError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "更新进度失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Node Status Change — 图谱节点状态变化 → 计划联动
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/node-status-change")
async def on_node_status_change(plan_id: int, body: NodeStatusChangeRequest):
    """图谱节点状态变化时同步计划，返回步骤联动建议。

    场景：
    - 节点被掌握（mastered）→ 计划中对应步骤可标记为 completed
    - 节点被遗忘（forgotten）→ 计划中对应步骤需重新安排复习
    - 节点被解锁（learning）→ 计划中对应步骤可从 locked 变为 pending
    """
    try:
        result = await _get_plan_center().node_status_change(
            plan_id=plan_id,
            plan=body.plan,
            steps=body.steps,
            masteries=body.masteries or {},
            node_id=body.node_id,
            old_status=body.old_status,
            new_status=body.new_status,
        )
        return api_success(result)
    except PlanNotFoundError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to handle node status change: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "节点状态联动失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Plan Status (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    """查询计划状态（含软着陆触发检测）。Java 传入 plan + steps 数据。"""
    try:
        return api_success(await _get_plan_center().plan_status(
            plan=body.plan, steps=body.steps,
        ))
    except PlanNotFoundError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get plan status: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "查询计划状态失败", status_code=500)


@router.post("/plans/status")
async def get_plan_status_legacy(body: PlanStatusRequest):
    """兼容旧路径：/internal/plans/status（无 path 参数 plan_id）。

    路径不携带 plan_id，响应中的 plan_id 取 body.plan.id。
    """
    try:
        return api_success(await _get_plan_center().plan_status(
            plan=body.plan, steps=body.steps,
        ))
    except PlanNotFoundError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get plan status: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "查询计划状态失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Regression Check
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/regression-check")
async def regression_check(plan_id: int, body: RegressionCheckRequest):
    """回归检测管线：出题 → 判分 → 重排。纯算法，不写 DB。"""
    try:
        plan_service = get_plan_service()
        plan = body.plan
        steps = body.steps
        days_idle = body.days_idle

        if not plan:
            return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

        paused_steps = [s for s in steps if s.get("status") in ("paused", "in_progress")]

        # ── 阶段 1: 无 answers → 出题 ──
        if not body.answers:
            if not paused_steps:
                return api_success({
                    "plan_id": plan_id,
                    "strategy": "continue",
                    "message": RETURN_MESSAGES["short"],
                    "questions": [],
                })

            paused_dicts = [
                {
                    "topic": s.get("topic"),
                    "mastery_current": s.get("mastery_current") or 0,
                    "topic_difficulty": s.get("topic_difficulty") or 3,
                    "review_count": s.get("review_count") or 0,
                }
                for s in paused_steps
            ]
            landing = plan_service.soft_landing(paused_dicts, days_idle)

            if landing["strategy"] == "continue":
                return api_success({
                    "plan_id": plan_id,
                    "strategy": landing["strategy"],
                    "message": landing["message"],
                    "questions": [],
                })

            exercise_agent = _get_exercise_agent()
            questions = []
            for node_name in landing["review_nodes"]:
                try:
                    ex_state = {"topic": node_name, "count": 1, "difficulty": "easy", "purpose": "warmup_not_exam"}
                    ex_result = await exercise_agent.run(ex_state)
                    qs = ex_result.get("questions", [])
                    for q in qs:
                        q["review_node"] = node_name
                    questions.extend(qs)
                except Exception as e:
                    logger.warning(f"Failed to generate warmup question for '{node_name}': {e}")

            return api_success({
                "plan_id": plan_id,
                "strategy": landing["strategy"],
                "message": landing["message"],
                "questions": questions,
            })

        # ── 阶段 2: 有 answers → 判分 + 重排 ──
        from app.services.evaluation_service import grade_choice, grade_short_answer

        decay_results = {}
        for step in steps:
            if step.get("status") in ("paused", "in_progress"):
                decayed = plan_service.estimate_decay(
                    step.get("mastery_current") or 0, days_idle,
                    step.get("topic_difficulty") or 3, step.get("review_count") or 0,
                )
                if decayed < 0.6:
                    decay_results[step.get("topic")] = "review" if decayed < 0.3 else "review_light"

        answers_by_topic = {}
        for ans in body.answers:
            topic = ans.get("topic", "")
            answers_by_topic.setdefault(topic, []).append(ans)

        # 计算每个 topic 的 mastery 更新
        mastery_updates = {}
        for topic, topic_answers in answers_by_topic.items():
            total_score = 0
            for ans in topic_answers:
                q_type = ans.get("question_type", "choice")
                user_answer = ans.get("user_answer", "")
                correct_answer = ans.get("correct_answer", "")
                if q_type == "choice":
                    grade_result = grade_choice(user_answer, correct_answer, ans.get("choices", []))
                else:
                    grade_result = await grade_short_answer(user_answer, correct_answer)
                total_score += grade_result.get("earned", 0)

            avg_score = total_score / len(topic_answers) if topic_answers else 0
            for step in steps:
                if step.get("topic") == topic:
                    prev_mastery = step.get("mastery_current") or 0
                    if avg_score >= 0.6:
                        new_m = plan_service.update_mastery(prev_mastery, "exercise_done", avg_score)
                    else:
                        new_m = plan_service.update_mastery(prev_mastery, "exercise_failed")
                    mastery_updates[topic] = {
                        "previous_mastery": prev_mastery,
                        "new_mastery": new_m,
                        "review_count": (step.get("review_count") or 0) + 1,
                        "step_id": step.get("id"),
                    }

        # 重排
        reordered_steps = None
        if decay_results:
            current_node = steps[0].get("knowledge_node_id", "") if steps else ""
            goal_node = steps[-1].get("knowledge_node_id", "") if steps else ""
            step_dicts = [
                {"topic": s.get("topic"), "status": s.get("status"), "step_order": s.get("step_order"),
                 "knowledge_node_id": s.get("knowledge_node_id") or "",
                 "mastery_current": s.get("mastery_current"), "topic_difficulty": s.get("topic_difficulty")}
                for s in steps
            ]
            reordered = plan_service.reorder_plan(
                step_dicts, decay_results, days_idle,
                current_topic=current_node, goal_topic=goal_node,
            )
            reordered_steps = [
                {"step_order": i + 1, "topic": r.get("topic"), "status": r.get("status"),
                 "mastery_current": r.get("mastery_current")}
                for i, r in enumerate(reordered)
            ]

        return api_success({
            "plan_id": plan_id,
            "strategy": "regression_check",
            "message": RETURN_MESSAGES["after_pass"] if not decay_results else RETURN_MESSAGES["after_fail"],
            "questions": [],
            "mastery_updates": mastery_updates,
            "reordered_steps": reordered_steps,
        })

    except Exception as e:
        logger.error(f"Failed regression check: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "回归检测失败，请稍后重试", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Review Schedule (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/review-schedule")
async def get_review_schedule(plan_id: int, body: ReviewScheduleRequest):
    """获取未来 N 天的复习日程。Java 传入 steps 数据。"""
    try:
        result = await _get_plan_center().review_schedule(
            plan_id=plan_id, steps=body.steps, days_ahead=body.days_ahead,
        )
        return api_success(result)
    except Exception as e:
        logger.error(f"Failed to get review schedule: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "获取复习日程失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Unified Chat (双层模式策略)
# ═══════════════════════════════════════════════════════════════════

_intent_extractor: IntentExtractor | None = None
_intent_extractor_lock = threading.Lock()


def _get_intent_extractor() -> IntentExtractor:
    global _intent_extractor
    if _intent_extractor is None:
        with _intent_extractor_lock:
            if _intent_extractor is None:
                _intent_extractor = IntentExtractor()
    return _intent_extractor


@router.post("/api/chat")
async def unified_chat(body: UnifiedChatRequest):
    return await _unified_chat(body)


async def _unified_chat(body: UnifiedChatRequest):
    """统一聊天路由：只做协议适配，业务编排全部在 ChatCenter.stream_chat()。

    职责（Task 3 收口）：
    1. sanitize_model + 基础输入处理；
    2. 调用 _get_chat_center().stream_chat(...)；
    3. 将 StreamEvent 转成 SSE 文本；
    4. 返回 StreamingResponse(sse_heartbeat_generator(...))。

    正文聚合、推荐抽取、多 done 收敛、缺 done 兜底、错误补发等
    聊天级终态策略已移入 ChatCenter.stream_chat()，API 不再重复实现。
    """
    body = sanitize_model(body)
    message = body.message.strip()

    chat_center = _get_chat_center()
    gen = chat_center.stream_chat(
        message=message,
        history=body.messages,
        mode=body.mode,
        student_profile=body.student_profile,
        user_id=body.user_id,
        conversation_id=body.conversation_id,
        style=body.style or "standard",
    )

    # 预取第一个事件：route 阶段异常在 HTTP 响应发送前暴露为 500，
    # 避免流已经发出 200 后内部再爆炸。
    try:
        first_event = await gen.__anext__()
    except Exception as e:
        logger.error(f"Chat pipeline failed before first event: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试", status_code=500)

    async def event_stream():
        yield first_event.to_sse()
        async for event in gen:
            yield event.to_sse()

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Inquiry Resolve
# ═══════════════════════════════════════════════════════════════════

@router.post("/inquiry/resolve")
async def inquiry_resolve(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后委派给 ResourceCenter 生成资源。"""
    body = sanitize_model(body)
    student_profile = body.student_profile

    inquiry = _get_inquiry_service()
    resolved = inquiry.resolve(
        body.original_message,
        body.answers,
        questions=body.questions or None,
        suggested_types=body.suggested_types or None,
        clarified_topic=body.clarified_topic or None,
    )

    topic = resolved.get("topic", body.original_message)
    context_note = resolved.get("context_note", "")
    suggested_types = resolved.get("suggested_types", [])
    # 取第一个推荐类型作为 resource_type（单 Agent 路由）
    primary_type = suggested_types[0] if suggested_types else None

    logger.info(
        "Inquiry resolved: topic=%s, types=%s, primary=%s, answer_count=%d",
        topic, suggested_types, primary_type, len(body.answers),
    )

    enriched_profile = dict(student_profile)
    enriched_profile["_inquiry_context"] = context_note

    async def event_stream():
        async for event in _get_resource_center().stream_generate(
            user_id=body.user_id,
            topic=topic,
            student_profile=enriched_profile,
            resource_type=primary_type or "",
        ):
            yield event.to_sse()

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/inquiry/resolve/plan")
async def inquiry_resolve_plan(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后调用 LearningPathWorkflow 生成学习路径。"""
    body = sanitize_model(body)
    student_profile = body.student_profile

    inquiry = _get_inquiry_service()
    resolved = inquiry.resolve(
        body.original_message,
        body.answers,
        questions=body.questions or None,
        suggested_types=body.suggested_types or None,
        clarified_topic=body.clarified_topic or None,
    )

    topic = resolved.get("topic", body.original_message)
    context_note = resolved.get("context_note", "")

    enriched_profile = dict(student_profile)
    enriched_profile["_inquiry_context"] = context_note

    path_workflow = _get_path_workflow()

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'path', 'content': f'正在为「{topic}」规划学习路径...'}, ensure_ascii=False)}\n\n"

            path_state = await path_workflow.run({
                "user_id": body.user_id,
                "student_profile": enriched_profile,
                "topic": topic,
            })

            steps = path_state.get("steps", [])
            concept_graph = path_state.get("concept_graph", {})
            path_summary = path_state.get("response", "")

            yield f"data: {json.dumps({'type': 'path', 'steps': steps}, ensure_ascii=False)}\n\n"

            if path_summary:
                for chunk in _sse_stream_chunks(path_summary):
                    await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            done_payload: dict = {
                "type": "done",
                "mode": "research",
                "plan": {
                    "title": f"{topic}学习计划",
                    "topic": topic,
                    "total_steps": len(steps),
                    "steps": steps,
                    "concept_graph": concept_graph,
                }
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Inquiry resolve plan error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '学习路径生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Conversation Summary (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/conversations/{conversation_id}/summary")
async def get_conversation_summary(conversation_id: int, body: SummaryRequest):
    """获取学习总结卡片。Java 传入原始消息列表，Python 用 LLM 生成总结。"""
    try:
        from app.utils.conversation_compress import format_messages_for_compress, llm_summarize

        messages_text = format_messages_for_compress(body.messages)
        summary = await llm_summarize("", messages_text)

        return api_success({
            "conversation_id": conversation_id,
            "summary": summary or "本次对话涵盖了多个学习主题。",
        })
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "生成总结卡片失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Eval Judge — 独立评测端点（绕过 Agent 包装，只调原 LLM）
# ═══════════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field


class JudgeRequest(BaseModel):
    message: str = Field(..., min_length=1, description="裁判提示词（含待评审内容）")
    system_prompt: str = Field(default="", description="可选 system prompt")


@router.post("/eval/judge")
async def eval_judge(body: JudgeRequest):
    """旁路评测：直接调用 LLM，不经任何 Agent 包装。

    与 /api/chat 的区别：
      - 不走 RouterAgent → Center → Agent pipeline
      - LLM 返回什么就输出什么，不对格式做任何加工
      - 仅用于自动化测试的 LLM 裁判评审

    安全：通过 EVAL_JUDGE_ENABLED 环境变量控制（默认关闭）。
    """
    if not os.getenv("EVAL_JUDGE_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        return api_error(ErrorCode.INVALID_REQUEST, "评测端点未启用", status_code=403)
    try:
        from app.services.llm_service import get_llm_service as _get_llm

        llm = _get_llm()
        messages = [{"role": "user", "content": body.message}]
        raw = await llm.chat(messages, system_prompt=body.system_prompt or "")
        return api_success({"response": raw})
    except Exception as e:
        logger.error(f"Eval judge failed: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, f"裁判调用失败: {e}", status_code=500)
