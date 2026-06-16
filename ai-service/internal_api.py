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

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse

from app.utils.sse_heartbeat import sse_heartbeat_generator
from app.api.errors import ErrorCode, api_error, api_success
from app.api.models import (
    ProfileChatRequest,
    ProfileWorkflowStatusRequest,
    ResourceGenRequest,
    ExportPptxRequest,
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
from app.events.types import StreamEvent, done_event
from app.services.intent_extractor import IntentExtractor
from app.centers.chat_center import ChatCenter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal")

_chat_center_singleton = None
_chat_center_lock = threading.Lock()

_profile_agent_singleton = None
_tutor_agent_singleton = None
_content_agent_singleton = None
_exercise_agent_singleton = None
_path_agent_singleton = None
_mindmap_agent_singleton = None
_code_agent_singleton = None
_profile_workflow_singleton = None
_resource_workflow_singleton = None
_path_workflow_singleton = None
_inquiry_service_singleton = None


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


_solve_agent_singleton = None


def _get_solve_agent():
    global _solve_agent_singleton
    if _solve_agent_singleton is None:
        from app.agents.solve_agent import SolveAgent
        _solve_agent_singleton = SolveAgent(use_mock_llm=_get_mock_flag())
    return _solve_agent_singleton


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


def _get_resource_workflow():
    global _resource_workflow_singleton
    if _resource_workflow_singleton is None:
        from app.workflows.resource_gen import ResourceGenWorkflow
        _resource_workflow_singleton = ResourceGenWorkflow(use_mock=_get_mock_flag())
    return _resource_workflow_singleton


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
    topic = body.topic.strip()
    student_profile = body.student_profile
    resource_type = body.resource_type

    workflow = _get_resource_workflow()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        try:
            async def run_workflow():
                try:
                    state = await workflow.run({
                        "user_id": body.user_id,
                        "topic": topic,
                        "student_profile": student_profile,
                        "resource_type": resource_type or "",
                        "event_queue": queue,
                    })
                    await queue.put(done_event({
                        "content_blocks": state.get("content_blocks", []),
                        "questions": state.get("questions", []),
                        "response": state.get("response", ""),
                        "error": state.get("error", ""),
                    }))
                except Exception as e:
                    logger.error(f"Resources generate workflow failed: {e}", exc_info=True)
                    await queue.put(done_event({"error": "资源生成失败，请稍后重试"}))

            task = asyncio.ensure_future(run_workflow())

            while True:
                event = await queue.get()
                if isinstance(event, StreamEvent):
                    yield event.to_sse()
                    if event.type == "done":
                        break
                else:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            await task
        except Exception as e:
            logger.error(f"Resources generate SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '资源生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Tutor Chat
# ═══════════════════════════════════════════════════════════════════

@router.post("/tutor/chat")
async def tutor_chat(body: TutorChatRequest):
    messages = body.messages
    student_profile = body.student_profile

    agent = _get_tutor_agent()

    async def event_stream():
        try:
            state = await agent.run({
                "messages": messages,
                "student_profile": student_profile,
            })

            response = state.get("response", "")
            domain = state.get("domain", "")

            if response:
                for chunk in _sse_stream_chunks(response):
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 后台增量画像提取，结果放进 done event
            profile_delta = None
            if response and messages:
                try:
                    p_agent = _get_profile_agent()
                    result = await p_agent.extract_and_merge(student_profile, messages)
                    if result.get("changed"):
                        profile_delta = result.get("profile")
                        logger.info("Background profile updated during tutor chat")
                except Exception as exc:
                    logger.warning("Background profile extract failed: %s", exc)

            done_payload: dict = {"type": "done", "domain": domain}
            if profile_delta:
                done_payload["profile_delta"] = profile_delta
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Tutor chat SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '答疑失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Exercise Generate
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/generate")
async def exercise_generate(body: ExerciseGenRequest):
    topic = body.topic.strip()
    knowledge_node_id = body.knowledge_node_id
    strategy = body.strategy
    count = body.count
    difficulty = body.difficulty
    student_profile = body.student_profile

    agent = _get_exercise_agent()
    display_topic = knowledge_node_id or topic

    async def event_stream():
        try:
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'plan', 'content': f'正在规划「{display_topic}」的练习题...'}, ensure_ascii=False)}\n\n"

            state = await agent.run({
                "topic": topic,
                "knowledge_node_id": knowledge_node_id,
                "strategy": strategy,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
            })

            await asyncio.sleep(0.5)
            num_q = len(state.get("questions", []))
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'generate', 'content': f'已生成 {num_q} 道题目'}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'questions': state.get('questions', [])}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Exercise generate SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '题目生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

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
_ALLOWED_EXTENSIONS = frozenset({".pptx", ".pdf"})


@router.get("/resources/download-pptx")
async def download_pptx(filename: str = Query(...)):
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ".pptx":
        return api_error(ErrorCode.VALIDATION_ERROR, "不支持的文件类型", status_code=400)
    file_path = os.path.join(_EXPORTS_DIR, safe_name)
    if not os.path.realpath(file_path).startswith(os.path.realpath(_EXPORTS_DIR)):
        return api_error(ErrorCode.VALIDATION_ERROR, "非法文件路径", status_code=400)
    if not os.path.exists(file_path):
        return api_error(ErrorCode.NOT_FOUND, "文件不存在或已过期", status_code=404)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
        return api_error(ErrorCode.VALIDATION_ERROR, "不支持的文件类型", status_code=400)
    file_path = os.path.join(_EXPORTS_DIR, safe_name)
    if not os.path.realpath(file_path).startswith(os.path.realpath(_EXPORTS_DIR)):
        return api_error(ErrorCode.VALIDATION_ERROR, "非法文件路径", status_code=400)
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
    question = body.question.strip()
    context = body.context

    agent = _get_solve_agent()

    async def event_stream():
        try:
            state = await agent.run({
                "question": question,
                "context": context,
            })

            steps = state.get("steps", [])
            if steps:
                yield f"data: {json.dumps({'type': 'steps', 'content': steps}, ensure_ascii=False)}\n\n"

            solution = state.get("solution", "")
            if solution:
                for chunk in _sse_stream_chunks(solution):
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            confidence = state.get("confidence_score")
            if confidence is not None:
                yield f"data: {json.dumps({'type': 'confidence', 'score': confidence}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Solve SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '解题功能暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Exercise Error Analysis
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/error-analysis")
async def exercise_error_analysis(body: ErrorAnalysisRequest):
    from app.utils.prompt_loader import load_prompt_file
    from app.utils.prompt_guard import sanitize_for_llm

    errors = body.errors
    level = body.level

    try:
        sys_prompt = load_prompt_file("tutor_agent", "error_analysis.yaml", key="system")
        user_tpl = load_prompt_file("tutor_agent", "error_analysis.yaml", key="user_template")
        from app.utils.prompt_loader import interpolate_variables

        sanitized_errors = [
            {k: sanitize_for_llm(v) if isinstance(v, str) else v for k, v in e.items()}
            for e in errors
        ]
        user_prompt = interpolate_variables(
            user_tpl,
            {"errors": json.dumps(sanitized_errors, ensure_ascii=False), "level": str(level)},
        )

        from app.services.llm_service import get_llm_service
        llm = get_llm_service()
        raw = await llm.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=sys_prompt,
        )
        from app.utils.json_parser import parse_llm_json
        result = parse_llm_json(raw, fallback={})
        return api_success(result)
    except Exception as e:
        logger.error(f"Error analysis failed: {e}")
        return api_error(ErrorCode.GENERATION_FAILED, "错题分析失败，请稍后重试", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Grade Exercise
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/grade")
async def grade_exercise(body: GradeRequest):
    from app.services.evaluation_service import grade_choice, grade_short_answer, grade_code

    if body.type == "choice":
        if body.user_answer is None or body.correct_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "user_answer and correct_answer are required",
            )
        result = grade_choice(
            body.user_answer,
            body.correct_answer,
            body.choices,
            multi=body.multi,
            points=body.points,
        )
    elif body.type == "code":
        if body.user_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD, "user_answer is required"
            )
        result = await grade_code(
            body.user_answer,
            body.reference_answer,
            body.rubric,
        )
    else:
        if body.user_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD, "user_answer is required"
            )
        result = await grade_short_answer(
            body.user_answer,
            body.reference_answer,
            body.rubric,
        )
    return api_success(result)


# ═══════════════════════════════════════════════════════════════════
# Evaluation Report
# ═══════════════════════════════════════════════════════════════════

@router.post("/evaluation/report")
async def get_evaluation_report(body: EvaluationReportRequest):
    from app.services.evaluation_service import generate_report

    report = generate_report(body.evaluation_results)
    return api_success(report)


# ═══════════════════════════════════════════════════════════════════
# Exercise Categorize
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/categorize")
async def categorize_exercises(body: CategorizeExerciseRequest):
    """将练习题匹配到知识图谱节点。"""
    from app.services.exercise_categorization_service import categorize_exercises as _categorize

    exercises = [ex.model_dump() for ex in body.exercises]
    results = await _categorize(exercises, body.knowledge_nodes, body.course_id)
    return api_success({"results": results})


# ═══════════════════════════════════════════════════════════════════
# Exercise Session Analytics
# ═══════════════════════════════════════════════════════════════════

@router.post("/exercise/session/analyze")
async def analyze_session(body: SessionAnalyzeRequest):
    """分析一次练习会话，返回逐知识点报告 + 掌握度更新建议。"""
    from app.services.exercise_analytics_service import analyze_session as _analyze

    records = [r.model_dump() for r in body.records]
    result = _analyze(records, body.masteries, body.course_id)
    return api_success(result)


@router.post("/exercise/dashboard")
async def exercise_dashboard(body: DashboardRequest):
    """练习仪表盘：练习统计 + 薄弱/强项 + 推荐节点。"""
    from app.services.exercise_analytics_service import get_dashboard as _dashboard

    records = [r.model_dump() for r in body.recent_records]
    result = _dashboard(body.user_id, body.masteries, records, body.course_id)
    return api_success(result)


@router.post("/exercise/profile/enrich")
async def enrich_profile(body: ProfileEnrichRequest):
    """练习数据反哺学生画像：合并薄弱点、强项、技能等级。"""
    from app.services.exercise_profile_service import enrich_profile as _enrich

    records = [r.model_dump() for r in body.recent_records]
    result = _enrich(body.user_id, body.student_profile, records, body.session_analysis)
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
    """一键生成学习计划。

    走新管线：GoalAgent → DecomposeAgent → ScheduleAgent。
    生成后自动为每个 step 匹配知识图谱节点（knowledge_node_id）。
    """
    try:
        user_id = body.user_id
        course_id = body.course_id
        student_profile = body.student_profile
        topic = body.topic or ""

        # ── 管线：Goal → Decompose → Schedule ─────────────────
        from app.agents.goal_agent import GoalAgent
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.schedule_agent import ScheduleAgent

        mock = _get_mock_flag()
        goal_agent = GoalAgent(use_mock_llm=mock)
        decompose_agent = DecomposeAgent(use_mock_llm=mock)
        schedule_agent = ScheduleAgent(use_mock_llm=mock)

        # Step 1: Goal extraction
        goal_state = await goal_agent.run({
            "input": topic,
            "context": "",
            "student_profile": student_profile,
        })
        goal = {
            "goal_title": goal_state.get("goal_title", topic),
            "target_topic": goal_state.get("target_topic", topic),
            "target_level": goal_state.get("target_level", "understand"),
            "deadline": goal_state.get("deadline", ""),
            "motivation": goal_state.get("motivation", ""),
            "constraints": goal_state.get("constraints", []),
        }

        # Step 2: Decomposition
        effective_topic = goal.get("target_topic") or topic
        decompose_state = await decompose_agent.run({
            "topic": effective_topic,
            "context": topic,
            "student_profile": student_profile,
        })
        decomposition = {
            "macro_topics": decompose_state.get("macro_topics", []),
            "micro_skills": decompose_state.get("micro_skills", []),
            "prerequisites": decompose_state.get("prerequisites", []),
        }

        # Step 3: Schedule generation
        schedule_state = await schedule_agent.run({
            "goal": goal,
            "decomposition": decomposition,
            "student_profile": student_profile,
            "existing_plan": {},
        })
        steps = schedule_state.get("steps", [])

        if not steps:
            return api_error(
                ErrorCode.GENERATION_FAILED, "未能生成学习计划，请确认输入更具体", status_code=400
            )

        # ── Step enrichment: 匹配 knowledge_node_id ────────────
        plan_steps = await _enrich_steps_with_nodes(steps, course_id)

        # ── Normalize milestones: 兼容字符串格式 → {milestone_id, after_step, description} ──
        raw_milestones = schedule_state.get("milestones", [])
        milestones = _normalize_milestones(raw_milestones, len(plan_steps))

        return api_success({
            "course_id": course_id,
            "total_steps": len(plan_steps),
            "steps": plan_steps,
            "title": schedule_state.get("plan_title", f"{effective_topic}学习计划"),
            "milestones": milestones,
            "estimated_days": schedule_state.get("estimated_days", 7),
            "daily_capacity": schedule_state.get("daily_capacity", 3),
            "concept_graph": decomposition,
            "summary": schedule_state.get("response", ""),
        })
    except Exception as e:
        logger.error(f"Failed to create plan from path: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "创建学习计划失败，请稍后重试", status_code=500)


async def _enrich_steps_with_nodes(steps: list[dict], course_id: str) -> list[dict]:
    """用知识图谱节点匹配每个 step 的 topic，打上 knowledge_node_id + suggested_resource_types。

    先用图谱已有节点精确匹配（name/id），匹配不到的用 LLM 分类兜底。
    """
    from app.services.exercise_categorization_service import categorize_exercises

    # Collect all graph nodes
    try:
        graph_service = _get_graph_service()
        all_nodes = graph_service.load_skeleton().get("nodes", [])
        dynamic_nodes = graph_service._all_nodes(course_id)
    except Exception as exc:
        logger.warning(f"Graph service unavailable during step enrichment: {exc}")
        all_nodes = []
        dynamic_nodes = []
    node_lookup: dict[str, str] = {}
    node_category: dict[str, str] = {}
    for n in dynamic_nodes:
        name = (n.get("name") or "").strip().lower()
        nid = (n.get("id") or "").strip()
        if name and nid:
            node_lookup[name] = nid
            node_category[name] = (n.get("category") or "").strip()

    def _suggest_resources(topic: str, category: str) -> list[str]:
        """根据知识点类别建议资源类型。"""
        cat_lower = category.lower()
        if cat_lower in ("基础", "foundation", "概念", "concept"):
            return ["document", "mindmap", "exercise"]
        elif cat_lower in ("算法", "algorithm", "代码", "code"):
            return ["document", "code_demo", "exercise", "mindmap"]
        elif cat_lower in ("应用", "application", "实战", "practice"):
            return ["document", "case_study", "code_demo", "exercise"]
        elif cat_lower in ("数学", "math", "理论", "theory"):
            return ["document", "formula_sheet", "exercise"]
        else:
            return ["document", "mindmap", "exercise"]

    # Try exact match first, collect unknowns for LLM classification
    unknowns: list[dict] = []
    plan_steps: list[dict] = []
    for i, step in enumerate(steps):
        topic = (step.get("topic") or "").strip()
        matched_id = node_lookup.get(topic.lower(), "")
        matched_cat = node_category.get(topic.lower(), "")

        if matched_id:
            plan_steps.append({
                "step_order": i + 1,
                "topic": topic,
                "knowledge_node_id": matched_id,
                "status": step.get("status", "pending"),
                "estimated_days": step.get("estimated_days", 1),
                "topic_difficulty": step.get("topic_difficulty", 3),
                "suggested_resource_types": _suggest_resources(topic, matched_cat),
            })
        else:
            unknowns.append({"index": i, "topic": topic, "step": step})

    # LLM classification for unmatched steps
    if unknowns and all_nodes:
        slim_nodes = [{"id": n.get("id",""), "name": n.get("name",""), "description": n.get("description","")} for n in all_nodes]
        exercises = [{"question": u["topic"], "answer": "", "question_type": "short_answer"} for u in unknowns]
        try:
            results = await categorize_exercises(exercises, slim_nodes, course_id)
            result_map = {r["index"]: r.get("knowledge_node_id", "") for r in results}
        except Exception as exc:
            logger.warning(f"Step enrichment LLM fallback failed: {exc}")
            result_map = {}

        for u in unknowns:
            step = u["step"]
            nid = result_map.get(u["index"], "")
            plan_steps.append({
                "step_order": u["index"] + 1,
                "topic": u["topic"],
                "knowledge_node_id": nid,
                "status": step.get("status", "pending"),
                "estimated_days": step.get("estimated_days", 1),
                "topic_difficulty": step.get("topic_difficulty", 3),
                "suggested_resource_types": _suggest_resources(u["topic"], ""),
            })

    # Sort by step_order
    plan_steps.sort(key=lambda s: s["step_order"])
    return plan_steps


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

        mock = _get_mock_flag()
        from app.agents.exercise_agent import ExerciseAgent
        exercise_agent = ExerciseAgent(use_mock_llm=mock)

        agent_state = await exercise_agent.run({
            "topic": step_topic,
            "knowledge_node_id": knowledge_node_id or None,
            "strategy": "review",
            "count": 3 if is_near_end else 2,
            "difficulty": "medium",
            "student_profile": {},
            "purpose": "consolidation",  # 触发 warmup 条件 → 轻松语气
        })

        questions = agent_state.get("questions", [])

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
    """返回今日应完成的步骤 + 每个步骤的资源建议。

    计算逻辑：
    1. 根据 plan.start_date + 累计 estimated_days 推算出「今天」对应的步骤区间
    2. 返回这些步骤的详情（含 knowledge_node_id + suggested_resource_types）
    3. 若 Java 传入 masteries，附带各节点的掌握度信息
    """
    from datetime import date, datetime as dt

    try:
        plan = body.plan
        steps = body.steps

        if not plan:
            return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

        # 确定起点日期
        start_str = body.start_date or plan.get("start_date") or plan.get("created_at")
        if start_str:
            try:
                if isinstance(start_str, str):
                    start_date = dt.fromisoformat(start_str.replace("Z", "+00:00")).date()
                else:
                    start_date = date.today()
            except (ValueError, TypeError):
                start_date = date.today()
        else:
            start_date = date.today()

        today = date.today()
        day_index = (today - start_date).days
        if day_index < 0:
            day_index = 0

        # 按累计 estimated_days 划分每天的步骤
        cumulative = 0
        today_steps: list[dict] = []
        completed_steps = plan.get("completed_steps") or 0
        total_steps = len(steps) if steps else plan.get("total_steps", 0)

        for s in sorted(steps, key=lambda x: x.get("step_order", 999)):
            step_order = s.get("step_order", 0)
            est = max(s.get("estimated_days", 1), 1)

            # 判断该 step 是否属于今天
            step_start_day = cumulative
            step_end_day = cumulative + est

            if step_start_day <= day_index < step_end_day:
                nid = s.get("knowledge_node_id", "")
                today_steps.append({
                    "step_order": step_order,
                    "topic": s.get("topic", ""),
                    "knowledge_node_id": nid,
                    "status": s.get("status", "pending"),
                    "estimated_days": est,
                    "topic_difficulty": s.get("topic_difficulty", 3),
                    "suggested_resource_types": s.get("suggested_resource_types", ["document", "exercise"]),
                    "day_progress": day_index - step_start_day + 1,
                    "day_total": est,
                    "current_mastery": body.masteries.get(nid) if nid else None,
                })

            cumulative = step_end_day

        # 若 today_steps 为空（计划已完成 / 超出范围），返回最近的未完成步骤
        if not today_steps and completed_steps < total_steps:
            pending = [s for s in steps if s.get("status") not in ("completed",)]
            if pending:
                s = pending[0]
                nid = s.get("knowledge_node_id", "")
                today_steps.append({
                    "step_order": s.get("step_order", 0),
                    "topic": s.get("topic", ""),
                    "knowledge_node_id": nid,
                    "status": s.get("status", "pending"),
                    "estimated_days": s.get("estimated_days", 1),
                    "topic_difficulty": s.get("topic_difficulty", 3),
                    "suggested_resource_types": s.get("suggested_resource_types", ["document", "exercise"]),
                    "day_progress": 1,
                    "day_total": 1,
                    "current_mastery": body.masteries.get(nid) if nid else None,
                    "note": "计划进度落后，显示下一个待完成步骤",
                })

        # 资源生成建议 — 为每个今日步骤提供可直接调用的 resource prompt
        resource_suggestions = []
        for ts in today_steps:
            resource_suggestions.append({
                "step_order": ts["step_order"],
                "topic": ts["topic"],
                "knowledge_node_id": ts.get("knowledge_node_id"),
                "resource_types": ts.get("suggested_resource_types", []),
                "gen_prompt": f"请为「{ts['topic']}」生成学习资源，难度等级 {ts.get('topic_difficulty', 3)}/5",
            })

        return api_success({
            "plan_id": plan_id,
            "today": today.isoformat(),
            "day_index": day_index,
            "total_days_elapsed": day_index + 1,
            "steps_due_today": today_steps,
            "resource_suggestions": resource_suggestions,
            "next_milestone": _compute_next_milestone(plan, completed_steps),
            "summary": (
                f"今日有 {len(today_steps)} 个学习步骤"
                if today_steps
                else "今日无待完成步骤，继续保持！"
            ),
        })
    except Exception as e:
        logger.error(f"Failed to get today tasks: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "获取今日任务失败", status_code=500)


def _compute_next_milestone(plan: dict, completed_steps: int) -> dict | None:
    """计算下一个里程碑信息。兼容字符串格式 milestone。"""
    milestones = plan.get("milestones") or []
    if not milestones:
        return None
    if isinstance(milestones[0], str):
        return None
    for m in sorted(milestones, key=lambda x: x.get("after_step", 999) if isinstance(x, dict) else 999):
        if not isinstance(m, dict):
            continue
        if m.get("after_step", 0) > completed_steps:
            return {
                "milestone_id": m.get("milestone_id", ""),
                "description": m.get("description", ""),
                "after_step": m.get("after_step", 0),
                "steps_remaining": m.get("after_step", 0) - completed_steps,
            }
    return None


def _normalize_milestones(raw: list, total_steps: int) -> list[dict]:
    """将 ScheduleAgent 返回的里程碑标准化为 {milestone_id, after_step, description}。

    输入可能是字符串列表（LLM 直接输出）或已是正确格式。
    """
    if not raw:
        return []
    if isinstance(raw[0], dict) and "milestone_id" in raw[0]:
        return raw
    normalized = []
    n = len(raw)
    for i, item in enumerate(raw):
        desc = item if isinstance(item, str) else item.get("description", str(item))
        after_step = round(total_steps * (i + 1) / (n + 1))
        normalized.append({
            "milestone_id": f"m{i + 1}",
            "after_step": after_step,
            "description": desc,
        })
    return normalized


# ═══════════════════════════════════════════════════════════════════
# Progress Update — 更新步骤进度 + 计算掌握度变化
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/progress")
async def update_plan_progress(plan_id: int, body: ProgressUpdateRequest):
    """Java 在用户完成步骤学习/练习后调用。Python 计算掌握度变化并返回更新后的步骤列表。

    匹配前端对接文档 3.5 节规范。
    """
    try:
        plan = body.plan
        steps = body.steps
        masteries = body.masteries or {}

        if not plan:
            return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

        plan_service = get_plan_service()

        # ── 定位目标步骤 ─────────────────────────────
        target_step = None
        step_idx = -1
        for i, s in enumerate(steps):
            if body.step_id is not None and body.step_id > 0 and s.get("id") == body.step_id:
                target_step = s
                step_idx = i
                break
            if body.step_order is not None and body.step_order > 0 and s.get("step_order") == body.step_order:
                target_step = s
                step_idx = i
                break

        if target_step is None:
            return api_error(ErrorCode.NOT_FOUND, f"步骤 step_id={body.step_id} step_order={body.step_order} 不存在", status_code=404)

        # ── 计算掌握度变化 ───────────────────────────
        knowledge_node_id = target_step.get("knowledge_node_id", "")
        old_mastery = masteries.get(knowledge_node_id, target_step.get("mastery_current", 0.5)) if knowledge_node_id else 0.5

        event_type = "exercise_done" if body.activity_type in ("exercise", "quiz") else "resource_viewed"
        new_mastery = plan_service.update_mastery(
            old_mastery,
            event_type,
            score=body.score
        )

        mastery_updates: dict[str, dict] = {}
        if knowledge_node_id:
            mastery_updates[knowledge_node_id] = {
                "old_mastery": old_mastery,
                "new_mastery": new_mastery,
                "delta": round(new_mastery - old_mastery, 2),
                "event_type": event_type,
            }

        # ── 更新步骤状态 ─────────────────────────────
        updated_steps = list(steps)  # shallow copy
        updated_target = dict(target_step)
        updated_target["status"] = body.status
        if body.score is not None:
            updated_target["score"] = body.score
        updated_target["mastery_current"] = new_mastery
        updated_target["activity_type"] = body.activity_type
        updated_target["duration_minutes"] = body.duration_minutes
        if step_idx >= 0:
            updated_steps[step_idx] = updated_target

        # ── 里程碑进度 ─────────────────────────────
        completed_count = sum(1 for s in updated_steps if s.get("status") == "completed")
        next_milestone = _compute_next_milestone(plan, completed_count)

        return api_success({
            "plan_id": plan_id,
            "updated_step": {
                "step_order": updated_target.get("step_order"),
                "topic": updated_target.get("topic"),
                "knowledge_node_id": knowledge_node_id,
                "status": body.status,
                "score": body.score,
                "mastery_current": new_mastery,
                "activity_type": body.activity_type,
                "duration_minutes": body.duration_minutes,
            },
            "mastery_updates": mastery_updates,
            "completed_steps": completed_count,
            "total_steps": plan.get("total_steps", len(steps)),
            "progress_pct": round(completed_count / max(plan.get("total_steps", len(steps)), 1) * 100),
            "next_milestone": next_milestone,
            "updated_steps": updated_steps,
        })
    except Exception as e:
        logger.error(f"Failed to update progress: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "更新进度失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Node Status Change — 图谱节点状态变化 → 计划联动
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/node-status-change")
async def on_node_status_change(plan_id: int, body: NodeStatusChangeRequest):
    """图谱节点状态变化时同步计划。Java 调此端点获取计划的调整建议。

    场景：
    - 节点被掌握（mastered）→ 计划中对应步骤可标记为 completed
    - 节点被遗忘（forgotten）→ 计划中对应步骤需重新安排复习
    - 节点被解锁（learning）→ 计划中对应步骤可从 locked 变为 pending
    """
    try:
        plan = body.plan
        steps = body.steps
        node_id = body.node_id
        new_status = body.new_status
        old_status = body.old_status
        masteries = body.masteries or {}

        if not plan or not steps:
            return api_error(ErrorCode.NOT_FOUND, "计划或步骤数据缺失", status_code=404)

        plan_service = get_plan_service()

        # ── 找到 node_id 对应的计划步骤 ─────────────
        affected_steps: list[dict] = []
        unaffected_steps: list[dict] = []
        for s in steps:
            sid = s.get("knowledge_node_id", "")
            if sid == node_id:
                affected_steps.append(s)
            else:
                unaffected_steps.append(s)

        plan_actions: list[dict] = []
        updated_steps = list(steps)

        for s in affected_steps:
            old_step_status = s.get("status", "")
            current_mastery = masteries.get(node_id, s.get("mastery_current", 0.5))

            if new_status == "mastered":
                new_step_status = "completed"
                action_msg = f"步骤「{s.get('topic')}」对应节点已掌握，建议标记为完成"
                plan_actions.append({
                    "step_order": s.get("step_order"),
                    "topic": s.get("topic"),
                    "action": "mark_completed",
                    "old_status": old_step_status,
                    "new_status": new_step_status,
                    "message": action_msg,
                })

            elif new_status == "forgotten":
                new_step_status = "review"
                # 计算衰减后的掌握度
                decayed = plan_service.estimate_decay(
                    current_mastery, days_since_review=14,
                    topic_difficulty=s.get("topic_difficulty", 3),
                )
                action_msg = f"步骤「{s.get('topic')}」对应节点已遗忘（掌握度 {decayed}），建议安排复习"
                plan_actions.append({
                    "step_order": s.get("step_order"),
                    "topic": s.get("topic"),
                    "action": "schedule_review",
                    "old_status": old_step_status,
                    "new_status": new_step_status,
                    "decayed_mastery": decayed,
                    "message": action_msg,
                })

            elif new_status == "learning" and old_status in ("locked", ""):
                new_step_status = "pending"
                action_msg = f"步骤「{s.get('topic')}」前置条件满足，已解锁"
                plan_actions.append({
                    "step_order": s.get("step_order"),
                    "topic": s.get("topic"),
                    "action": "unlock_step",
                    "old_status": old_step_status,
                    "new_status": new_step_status,
                    "message": action_msg,
                })

            elif new_status == "locked":
                new_step_status = "locked"
                action_msg = f"步骤「{s.get('topic')}」前置条件不满足，已重新锁定"
                plan_actions.append({
                    "step_order": s.get("step_order"),
                    "topic": s.get("topic"),
                    "action": "lock_step",
                    "old_status": old_step_status,
                    "new_status": new_step_status,
                    "message": action_msg,
                })
            else:
                continue

            # 更新步骤
            for i, us in enumerate(updated_steps):
                if us.get("step_order") == s.get("step_order"):
                    updated_steps[i] = {**us, "status": new_step_status, "mastery_current": current_mastery}
                    break

        # ── 检查是否所有步骤已完成 → 计划可关闭 ────
        completed_count = sum(1 for s in updated_steps if s.get("status") == "completed")
        total = len(updated_steps)
        plan_status = plan.get("status", "active")
        if completed_count >= total and plan_status != "completed":
            plan_status = "completed"
            plan_actions.append({
                "step_order": 0,
                "topic": "",
                "action": "complete_plan",
                "old_status": plan.get("status"),
                "new_status": "completed",
                "message": "所有步骤已完成，建议将计划标记为完成",
            })

        next_milestone = _compute_next_milestone(plan, completed_count)

        return api_success({
            "plan_id": plan_id,
            "node_id": node_id,
            "new_status": new_status,
            "affected_steps_count": len(affected_steps),
            "plan_actions": plan_actions,
            "updated_steps": updated_steps,
            "plan_status": plan_status,
            "completed_steps": completed_count,
            "total_steps": total,
            "progress_pct": round(completed_count / max(total, 1) * 100),
            "next_milestone": next_milestone,
            "summary": (
                f"节点状态变更影响 {len(affected_steps)} 个计划步骤"
                if affected_steps
                else "此节点状态变更不影响当前计划的步骤"
            ),
        })
    except Exception as e:
        logger.error(f"Failed to handle node status change: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "节点状态联动失败", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Plan Status (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    """查询计划状态（含软着陆触发检测）。Java 传入 plan + steps 数据。"""
    return await _get_plan_status_core(plan_id, body)


@router.post("/plans/status")
async def get_plan_status_legacy(body: PlanStatusRequest):
    """兼容旧路径：/internal/plans/status（无 path 参数 plan_id）。

    从 body.plan.id 中提取 plan_id 后复用核心逻辑。
    """
    plan_id = 0
    if body.plan and isinstance(body.plan.get("id"), int):
        plan_id = body.plan["id"]
    return await _get_plan_status_core(plan_id, body)


async def _get_plan_status_core(plan_id: int, body: PlanStatusRequest):
    """查询计划状态核心逻辑。"""
    from datetime import datetime, timezone

    try:
        plan = body.plan
        steps = body.steps

        if not plan:
            return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

        days_idle = 0
        last_activity = plan.get("last_activity_at")
        if last_activity:
            now = datetime.now(timezone.utc)
            try:
                if isinstance(last_activity, str):
                    dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                    delta = now - dt
                    days_idle = delta.days
            except (ValueError, TypeError):
                pass

        plan_service = get_plan_service()

        paused_steps = [s for s in steps if s.get("status") in ("paused", "in_progress")]
        soft_landing = None
        if plan.get("status") == "paused" and days_idle > 0:
            paused_dicts = [
                {
                    "topic": s.get("topic"),
                    "mastery_current": s.get("mastery_current") or 0,
                    "topic_difficulty": s.get("topic_difficulty") or 3,
                    "review_count": s.get("review_count") or 0,
                }
                for s in paused_steps
            ]
            soft_landing = plan_service.soft_landing(paused_dicts, days_idle)
            soft_landing["days_idle"] = days_idle

        steps_data = []
        for s in steps:
            step_dict = {
                "id": s.get("id"),
                "step_order": s.get("step_order"),
                "topic": s.get("topic"),
                "knowledge_node_id": s.get("knowledge_node_id"),
                "status": s.get("status"),
                "topic_difficulty": s.get("topic_difficulty"),
                "mastery_current": s.get("mastery_current"),
            }
            if s.get("status") in ("paused", "in_progress") and days_idle > 0:
                decayed = plan_service.estimate_decay(
                    s.get("mastery_current") or 0, days_idle,
                    s.get("topic_difficulty") or 3, s.get("review_count") or 0,
                )
                step_dict["decayed_mastery"] = decayed
            steps_data.append(step_dict)

        # ── Milestone progress ─────────────────────────────
        completed_steps = plan.get("completed_steps") or 0
        next_milestone = _compute_next_milestone(plan, completed_steps)
        milestone_progress = None
        if next_milestone:
            milestone_progress = {
                "current": completed_steps,
                "target": next_milestone["after_step"],
                "remaining": next_milestone["steps_remaining"],
                "pct": round(completed_steps / next_milestone["after_step"] * 100) if next_milestone["after_step"] > 0 else 100,
            }

        return api_success({
            "plan_id": plan.get("id"),
            "user_id": plan.get("user_id"),
            "status": plan.get("status"),
            "total_steps": plan.get("total_steps"),
            "completed_steps": completed_steps,
            "days_idle": days_idle,
            "soft_landing": soft_landing,
            "steps": steps_data,
            "next_milestone": next_milestone,
            "milestone_progress": milestone_progress,
        })
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
        steps = body.steps
        days_ahead = body.days_ahead

        from dataclasses import dataclass

        @dataclass
        class StepProxy:
            id: int; status: str; topic: str; topic_difficulty: int
            review_count: int; mastery_current: float; last_review_at: str | None
            knowledge_node_id: str

        step_proxies = []
        for s in steps:
            step_proxies.append(StepProxy(
                id=s.get("id", 0),
                status=s.get("status", ""),
                topic=s.get("topic", ""),
                topic_difficulty=s.get("topic_difficulty") or 3,
                review_count=s.get("review_count") or 0,
                mastery_current=s.get("mastery_current") or 0,
                last_review_at=s.get("last_review_at"),
                knowledge_node_id=s.get("knowledge_node_id", ""),
            ))

        plan_service = get_plan_service()
        schedule = plan_service.get_review_schedule(step_proxies, days_ahead)

        high_count = sum(1 for s in schedule if s["urgency"] == "high")
        medium_count = sum(1 for s in schedule if s["urgency"] == "medium")

        return api_success({
            "plan_id": plan_id,
            "days_ahead": days_ahead,
            "total_reviews": len(schedule),
            "high_urgency": high_count,
            "medium_urgency": medium_count,
            "schedule": schedule,
        })
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
    message = body.message.strip()
    history = body.messages
    user_msg = {"role": "user", "content": message}
    messages = history + [user_msg]

    chat_center = _get_chat_center()
    plan = await chat_center.route(
        message=message,
        mode=body.mode,
        student_profile=body.student_profile,
        context={
            "messages": messages,
            "style": body.style or "standard",
            "user_id": body.user_id,
            "conversation_id": body.conversation_id,
        },
    )

    async def event_stream():
        assistant_content = ""
        pending_done: list[str] = []

        try:
            async for event in chat_center.execute(plan):
                if event.type == "content" and event.data:
                    if isinstance(event.data, str):
                        assistant_content += event.data
                    elif isinstance(event.data, dict):
                        assistant_content += event.data.get("content", "")
                sse = event.to_sse()

                # Defer DONE event so recommendation can be inserted before it
                if event.type == "done":
                    pending_done.append(sse)
                    continue

                yield sse
        except Exception as e:
            logger.error(f"Center pipeline error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '处理失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        # Check for exercise recommendation (before DONE)
        try:
            if assistant_content.strip():
                extracted = await extract_knowledge_nodes(
                    course_id="ai_intro",
                    user_message=message,
                    assistant_reply=assistant_content[:2000],
                )
                primary_nodes = extracted.get("primary", [])
                if primary_nodes:
                    node = primary_nodes[0]
                    from app.events.types import recommendation_event
                    rec = recommendation_event(
                        knowledge_node_id=node.get("id", ""),
                        node_name=node.get("name", ""),
                    )
                    yield rec.to_sse()
        except Exception as exc:
            logger.warning(f"Recommendation check skipped: {exc}")

        # Yield deferred DONE event(s)
        for sse in pending_done:
            yield sse

        # Guarantee a DONE event if none was emitted
        if not pending_done:
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# Inquiry Resolve
# ═══════════════════════════════════════════════════════════════════

@router.post("/inquiry/resolve")
async def inquiry_resolve(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后调用 ResourceGenWorkflow 生成资源。"""
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
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        try:
            async def run_workflow():
                try:
                    workflow = _get_resource_workflow()
                    state = await workflow.run({
                        "user_id": body.user_id,
                        "topic": topic,
                        "student_profile": enriched_profile,
                        "resource_type": primary_type or "",
                        "event_queue": queue,
                    })
                    await queue.put(done_event({
                        "content_blocks": state.get("content_blocks", []),
                        "questions": state.get("questions", []),
                        "response": state.get("response", ""),
                        "error": state.get("error", ""),
                    }))
                except Exception as e:
                    logger.error(f"Inquiry resolve workflow failed: {e}", exc_info=True)
                    await queue.put(done_event({"error": "资源生成失败，请稍后重试"}))

            task = asyncio.ensure_future(run_workflow())

            while True:
                event = await queue.get()
                if isinstance(event, StreamEvent):
                    yield event.to_sse()
                    if event.type == "done":
                        break
                else:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            await task
        except Exception as e:
            logger.error(f"Inquiry resolve SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '资源生成失败'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/inquiry/resolve/plan")
async def inquiry_resolve_plan(body: InquiryResolveRequest):
    """接收用户对追问的回答，合并后调用 LearningPathWorkflow 生成学习路径。"""
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
