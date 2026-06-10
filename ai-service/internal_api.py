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
    PlanStatusRequest,
    ReviewScheduleRequest,
    SummaryRequest,
)
from app.services.plan_service import get_plan_service
from app.services.plan_constants import RETURN_MESSAGES
from app.events.types import StreamEvent, done_event
from app.services.intent_extractor import IntentExtractor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal")

_profile_agent_singleton = None
_tutor_agent_singleton = None
_content_agent_singleton = None
_exercise_agent_singleton = None
_path_agent_singleton = None
_mindmap_agent_singleton = None
_reading_agent_singleton = None
_code_agent_singleton = None
_profile_workflow_singleton = None
_resource_workflow_singleton = None
_path_workflow_singleton = None
_inquiry_service_singleton = None


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


def _get_reading_agent():
    global _reading_agent_singleton
    if _reading_agent_singleton is None:
        from app.agents.reading_agent import ReadingAgent
        _reading_agent_singleton = ReadingAgent(use_mock_llm=_get_mock_flag())
    return _reading_agent_singleton


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

    workflow = _get_resource_workflow()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        try:
            async def run_workflow():
                try:
                    state = await workflow.run({
                        "user_id": body.user_id,
                        "topic": topic,
                        "student_profile": student_profile,
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
    count = body.count
    difficulty = body.difficulty
    student_profile = body.student_profile

    agent = _get_exercise_agent()

    async def event_stream():
        try:
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'plan', 'content': f'正在规划「{topic}」的练习题...'}, ensure_ascii=False)}\n\n"

            state = await agent.run({
                "topic": topic,
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

    try:
        state = await workflow.run({
            "user_id": user_id,
            "student_profile": student_profile,
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


@router.get("/resources/download-pptx")
async def download_pptx(filename: str = Query(...)):
    safe_name = os.path.basename(filename)
    output_dir = os.path.join(os.path.dirname(__file__), "exports")
    file_path = os.path.join(output_dir, safe_name)

    if not os.path.exists(file_path):
        return api_error(ErrorCode.NOT_FOUND, "文件不存在或已过期", status_code=404)

    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
    from app.services.evaluation_service import grade_choice, grade_short_answer

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
        graph = await graph_service.get_graph(masteries=body.masteries)
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


# ═══════════════════════════════════════════════════════════════════
# Create Plan From Path
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/create-from-path")
async def create_plan_from_path(body: CreatePlanFromPathRequest):
    """一键生成学习路径。返回 steps + concept_graph，Java 自行创建 plan。"""
    try:
        user_id = body.user_id
        course_id = body.course_id
        student_profile = body.student_profile

        path_workflow = _get_path_workflow()
        path_state = await path_workflow.run({
            "user_id": user_id,
            "student_profile": student_profile,
        })

        steps = path_state.get("steps", [])
        concept_graph = path_state.get("concept_graph", {})

        if not steps:
            return api_error(
                ErrorCode.GENERATION_FAILED, "未能生成学习路径，请确认画像已构建", status_code=400
            )

        # 为每个 step 匹配 knowledge_node_id
        node_map = {}
        for node in concept_graph.get("nodes", []):
            node_map[node.get("name", "")] = node.get("id", "")
            node_map[node.get("label", "")] = node.get("id", "")

        plan_steps = []
        for i, step in enumerate(steps):
            topic = step.get("topic", "")
            knowledge_node_id = node_map.get(topic, "")
            plan_steps.append({
                "step_order": i + 1,
                "topic": topic,
                "knowledge_node_id": knowledge_node_id,
                "status": step.get("status", "pending"),
                "estimated_days": step.get("estimated_days", 1),
                "topic_difficulty": 3,
            })

        return api_success({
            "course_id": course_id,
            "total_steps": len(steps),
            "steps": plan_steps,
            "concept_graph": concept_graph,
            "summary": path_state.get("response", ""),
        })
    except Exception as e:
        logger.error(f"Failed to create plan from path: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "创建学习计划失败，请稍后重试", status_code=500)


# ═══════════════════════════════════════════════════════════════════
# Plan Status (changed from GET to POST)
# ═══════════════════════════════════════════════════════════════════

@router.post("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, body: PlanStatusRequest):
    """查询计划状态（含软着陆触发检测）。Java 传入 plan + steps 数据。"""
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

        return api_success({
            "plan_id": plan.get("id"),
            "user_id": plan.get("user_id"),
            "status": plan.get("status"),
            "total_steps": plan.get("total_steps"),
            "completed_steps": plan.get("completed_steps"),
            "days_idle": days_idle,
            "soft_landing": soft_landing,
            "steps": steps_data,
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


_INTENT_MODE_MAP: dict[str, str] = {
    "exercise_gen": "exercise",
    "resource_gen": "resource",
    "tutor_question": "tutor",
    "learning_path": "research",
    "solve_problem": "solve",
    "flashcard_gen": "research",
    "profile_building": "tutor",
    "unknown": "tutor",
}


def _build_confirmation(intent: str, confidence: float) -> str | None:
    hints: dict[str, str] = {
        "exercise_gen": "检测到你可能想练习，需要切换到出题模式吗？",
        "resource_gen": "检测到你可能想生成学习资源，需要切换吗？",
        "solve_problem": "检测到你可能想解题，需要切换到解题模式吗？",
        "learning_path": "检测到你可能想规划学习路径，需要切换吗？",
        "flashcard_gen": "检测到你可能想深入学习，需要切换吗？",
    }
    if confidence < 0.8 and intent in hints:
        return hints[intent]
    return None


@router.post("/api/chat")
async def unified_chat(body: UnifiedChatRequest):
    """统一对话入口 — 双层模式策略。Architecture #2: Java 传入完整数据。"""
    message = body.message.strip()
    user_id = body.user_id
    mode = body.mode
    conversation_id = body.conversation_id
    style = body.style or "standard"
    student_profile = body.student_profile
    history = body.messages

    # ── 双层模式策略 ──
    intent_meta: dict | None = None

    if mode != "auto":
        effective_mode = mode
    else:
        extractor = _get_intent_extractor()
        result = await extractor.extract(message)
        effective_mode = _INTENT_MODE_MAP.get(result.intent, "tutor")
        intent_meta = {
            "detected_intent": result.intent,
            "confidence": result.confidence,
            "raw_message": result.raw_message,
        }
        if _build_confirmation(result.intent, result.confidence):
            intent_meta["confirmation_question"] = _build_confirmation(
                result.intent, result.confidence
            )

    # ── 构建完整消息列表 ──
    user_msg = {"role": "user", "content": message}
    messages = history + [user_msg]

    # ── 模式分发 ──
    if effective_mode == "resource":
        return await _resource_mode_dispatch(message, user_id, student_profile)
    elif effective_mode == "solve":
        return await _unified_solve_chat(message, messages, student_profile, conversation_id)
    elif effective_mode == "exercise":
        return await _unified_exercise_chat(message, messages, student_profile, conversation_id)
    elif effective_mode == "research":
        return await _unified_research_chat(message, messages, student_profile, conversation_id, user_id)
    else:  # tutor (兜底)
        return await _unified_tutor_chat(message, messages, student_profile, conversation_id, style, intent_meta)


# ── 资源模式分流 ─────────────────────────────────────────────────

async def _resource_mode_dispatch(message: str, user_id: int, student_profile: dict):
    """资源模式：先过 InquiryService 检查需求清晰度。"""
    inquiry = _get_inquiry_service()
    result = await inquiry.check(message, student_profile)

    if result.is_clear:
        return await resources_generate(ResourceGenRequest(
            topic=result.clarified_topic,
            user_id=user_id,
            student_profile=student_profile,
        ))

    return api_success({
        "type": "inquiry",
        "is_clear": False,
        "clarified_topic": result.clarified_topic,
        "questions": result.questions,
        "rationale": result.rationale,
    })


# ── Unified Dispatch: tutor ──────────────────────────────────────

async def _unified_tutor_chat(
    message: str, messages: list[dict], student_profile: dict,
    conversation_id: int | None, style: str = "standard",
    intent_meta: dict | None = None,
):
    """答疑模式"""
    # 计算苏格拉底追问轮次
    socratic_round = 0
    if style == "socratic":
        socratic_round = sum(
            1 for m in messages[-20:]
            if m.get("role") == "assistant" and m.get("mode") == "tutor:socratic"
        )

    agent = _get_tutor_agent()

    async def event_stream():
        try:
            state = await agent.run({
                "messages": messages,
                "student_profile": student_profile,
                "style": style,
                "socratic_round": socratic_round,
            })

            # 意图提示
            if intent_meta:
                hint = intent_meta.get("confirmation_question")
                if hint:
                    yield f"data: {json.dumps({'type': 'intent_hint', 'content': hint, 'detected_intent': intent_meta.get('detected_intent'), 'confidence': intent_meta.get('confidence')}, ensure_ascii=False)}\n\n"

            response = state.get("response", "")
            domain = state.get("domain", "")
            if response:
                for chunk in _sse_stream_chunks(response):
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            # 后台画像提取，结果放进 done event
            profile_delta = None
            if response:
                try:
                    p_agent = _get_profile_agent()
                    result = await p_agent.extract_and_merge(student_profile, messages)
                    if result.get("changed"):
                        profile_delta = result.get("profile")
                except Exception as exc:
                    logger.warning("Background profile extract failed: %s", exc)

            done_payload: dict = {"type": "done", "domain": domain}
            if conversation_id:
                done_payload["conversation_id"] = conversation_id
            if profile_delta:
                done_payload["profile_delta"] = profile_delta
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Unified tutor chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '答疑失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ── Unified Dispatch: solve ──────────────────────────────────────

async def _unified_solve_chat(
    message: str, messages: list[dict], student_profile: dict,
    conversation_id: int | None,
):
    """解题模式"""
    context_parts = []
    for m in messages[-6:]:
        role_label = "学生" if m.get("role") == "user" else "AI"
        ctx = m.get("content", "")[:200]
        context_parts.append(f"[{role_label}]: {ctx}")
    context = "\n".join(context_parts)

    agent = _get_solve_agent()

    async def event_stream():
        try:
            state = await agent.run({
                "question": message,
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

            done_payload: dict = {"type": "done"}
            if conversation_id:
                done_payload["conversation_id"] = conversation_id
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Unified solve chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '解题失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ── Unified Dispatch: exercise ───────────────────────────────────

async def _unified_exercise_chat(
    message: str, messages: list[dict], student_profile: dict,
    conversation_id: int | None,
):
    """练习模式"""
    extractor = _get_intent_extractor()
    intent_result = await extractor.extract(message)
    topic = intent_result.params.get("topic", message)
    count = min(intent_result.params.get("count", 3), 10)
    difficulty = intent_result.params.get("difficulty", "medium")

    agent = _get_exercise_agent()

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'plan', 'content': f'正在为「{topic}」准备{count}道{difficulty}难度的练习题...'}, ensure_ascii=False)}\n\n"

            state = await agent.run({
                "topic": topic,
                "count": count,
                "difficulty": difficulty,
                "student_profile": student_profile,
            })

            questions = state.get("questions", [])
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'generate', 'content': f'已生成 {len(questions)} 道题目'}, ensure_ascii=False)}\n\n"

            done_payload: dict = {
                "type": "done",
                "questions": questions,
            }
            if conversation_id:
                done_payload["conversation_id"] = conversation_id
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Unified exercise chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '练习题生成失败'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


# ── Unified Dispatch: research ───────────────────────────────────

async def _unified_research_chat(
    message: str, messages: list[dict], student_profile: dict,
    conversation_id: int | None, user_id: int,
):
    """研究模式：学习路径 + 资源组合"""
    extractor = _get_intent_extractor()
    intent_result = await extractor.extract(message)
    topic = intent_result.params.get("topic", message)

    path_workflow = _get_path_workflow()

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'path', 'content': f'正在为「{topic}」规划学习路径...'}, ensure_ascii=False)}\n\n"

            path_state = await path_workflow.run({
                "user_id": user_id,
                "student_profile": student_profile,
            })

            steps = path_state.get("steps", [])
            path_summary = path_state.get("response", "")

            yield f"data: {json.dumps({'type': 'path', 'steps': steps}, ensure_ascii=False)}\n\n"

            if path_summary:
                for chunk in _sse_stream_chunks(path_summary):
                    await asyncio.sleep(0.02)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            done_payload: dict = {"type": "done"}
            if conversation_id:
                done_payload["conversation_id"] = conversation_id
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Unified research chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '研究模式暂时不可用'}, ensure_ascii=False)}\n\n"
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

    logger.info(
        "Inquiry resolved: topic=%s, types=%s, answer_count=%d",
        topic, suggested_types, len(body.answers),
    )

    enriched_profile = dict(student_profile)
    enriched_profile["_inquiry_context"] = context_note
    enriched_profile["_suggested_types"] = suggested_types

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        try:
            async def run_workflow():
                try:
                    workflow = _get_resource_workflow()
                    state = await workflow.run({
                        "user_id": body.user_id,
                        "topic": topic,
                        "student_profile": enriched_profile,
                        "event_queue": queue,
                        "suggested_types": suggested_types,
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
