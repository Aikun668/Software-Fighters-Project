import asyncio
import json
import logging
import os
import re
import threading
import time

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select

from app.utils.sse_heartbeat import sse_heartbeat_generator
from app.api.errors import ErrorCode, api_error, api_success
from app.db.database import get_db
from app.api.models import (
    ProfileChatRequest,
    ResourceGenRequest,
    ExportPptxRequest,
    TutorChatRequest,
    ExerciseGenRequest,
    GradeRequest,
    EvaluationReportRequest,
    SolveRequest,
    ErrorAnalysisRequest,
    UnifiedChatRequest,
    PlanCreateRequest,
    PlanProgressRequest,
    PlanResumeRequest,
    RegressionCheckRequest,
    NodeStatusChangeRequest,
)
from app.services.plan_service import get_plan_service
from app.services.plan_constants import RETURN_MESSAGES
from app.events.types import StreamEvent, done_event
from app.services.conversation_service import get_conversation_service
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


# Mock 模式已全面废弃，始终使用真实 LLM 调用
# 保留 _get_mock_flag() 接口以兼容存量调用方
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


async def _load_profile(user_id: int) -> dict:
    from app.services.profile_service import get_profile_service
    profile = await get_profile_service().get_profile(user_id)
    return profile or {}


# ── 多模态消息构建 ──────────────────────────────────────────────

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _extract_text_from_multimodal(content) -> str:
    """从多模态 content（字符串或数组）中提取纯文本，用于 RAG 检索和 DB 持久化"""
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


def _is_internal_url(url: str) -> bool:
    """检测 URL 是否指向内网/云元数据地址，防御 SSRF。"""
    return bool(_SSRF_BLOCKED_NETWORKS.search(url))


def _build_multimodal_message(text: str, images: list[str] | None) -> dict:
    """构建用户消息 dict，支持多模态图片。

    纯文本 → {"role": "user", "content": "text"}
    带图片 → {"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}
    """
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
            # 防御 SSRF：只允许常见域名模式，拒绝内网/云元数据地址
            if _is_internal_url(img):
                logger.warning(f"Rejected internal/infra URL for SSRF prevention: {img[:80]}")
                continue
            url = img
        else:
            # 裸 base64，默认当作 JPEG
            url = f"data:image/jpeg;base64,{img}"
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    if not content_parts:
        return {"role": "user", "content": text}
    # 如果只有文本没有图片，降级为纯字符串格式
    if len(content_parts) == 1 and content_parts[0].get("type") == "text":
        return {"role": "user", "content": text}
    return {"role": "user", "content": content_parts}


@router.post("/profile/chat")
async def profile_chat(body: ProfileChatRequest):
    messages = body.messages
    user_id = body.user_id

    current_profile = await _load_profile(user_id)
    workflow = _get_profile_workflow()

    async def event_stream():
        try:
            state = await workflow.run({
                "messages": messages,
                "user_id": user_id,
                "current_profile": current_profile,
            })

            response = state.get("response", "")
            if response:
                for char in response:
                    await asyncio.sleep(0.04)
                    yield f"data: {json.dumps({'type': 'token', 'content': char}, ensure_ascii=False)}\n\n"

            if state.get("profile_changed"):
                yield f"data: {json.dumps({'type': 'profile_update', 'content': state.get('current_profile', {})}, ensure_ascii=False)}\n\n"

            if state.get("profile_complete"):
                yield f"data: {json.dumps({'type': 'profile_complete', 'filled_dimensions': state.get('filled_dimensions', 0)}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Profile chat SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '画像对话失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/resources/generate")
async def resources_generate(body: ResourceGenRequest):
    topic = body.topic.strip()
    user_id = body.user_id
    student_profile = body.student_profile

    if not student_profile:
        student_profile = await _load_profile(user_id)

    workflow = _get_resource_workflow()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        try:
            # Kick off the workflow in background — it pushes StreamEvent to queue
            async def run_workflow():
                try:
                    state = await workflow.run({
                        "user_id": user_id,
                        "topic": topic,
                        "student_profile": student_profile,
                        "event_queue": queue,
                    })
                    # Push final done event with results
                    await queue.put(done_event({
                        "content_blocks": state.get("content_blocks", []),
                        "questions": state.get("questions", []),
                        "resource_ids": state.get("resource_ids", []),
                        "response": state.get("response", ""),
                        "error": state.get("error", ""),
                    }))
                except Exception as e:
                    logger.error(f"Resources generate workflow failed: {e}")
                    await queue.put(done_event({"error": str(e)}))

            task = asyncio.ensure_future(run_workflow())

            # Stream events from queue as they arrive
            while True:
                event = await queue.get()
                if isinstance(event, StreamEvent):
                    yield event.to_sse()
                    if event.type == "done":
                        break
                else:
                    # Backward compat: raw dicts
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            await task
        except Exception as e:
            logger.error(f"Resources generate SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '资源生成失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/tutor/chat")
async def tutor_chat(body: TutorChatRequest):
    user_id = body.user_id
    student_profile = body.student_profile
    content = body.content
    messages = body.messages
    conversation_id = body.conversation_id
    images = body.images

    # ── 新 API：content + conversation_id ──
    if content is not None and content.strip():
        conv_service = get_conversation_service()
        conv = await conv_service.get_or_create_conversation(user_id, conversation_id)
        history = await conv_service.load_history(conv.id)
        user_msg = _build_multimodal_message(content.strip(), images)
        messages = history + [user_msg]
        is_new_api = True
        # 用于 DB 持久化：只存文本部分（图片不跨轮携带）
        text_for_db = content.strip()
    # ── 旧 API：完整 messages 数组（向后兼容）──
    elif messages is not None and len(messages) > 0:
        is_new_api = False
    else:
        return api_error(ErrorCode.INVALID_REQUEST, "需要 content 或 messages 字段")

    if not student_profile:
        student_profile = await _load_profile(user_id)

    agent = _get_tutor_agent()

    async def event_stream():
        user_conversation_id = (
            conv.id if is_new_api else None
        )
        try:
            state = await agent.run({
                "messages": messages,
                "user_id": user_id,
                "student_profile": student_profile,
                "conversation_id": user_conversation_id,
            })

            response = state.get("response", "")

            # 发送会话元信息
            if user_conversation_id is not None:
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "meta", "conversation_id": user_conversation_id},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            # 持久化新消息（不阻塞流式输出，只存文本部分）
            if is_new_api and response:
                import asyncio as _asyncio

                def _log_save_error(task):
                    try:
                        task.result()
                    except Exception as exc:
                        logger.warning(f"Background save_messages failed: {exc}")

                save_task = _asyncio.ensure_future(
                    conv_service.save_messages(
                        user_conversation_id,
                        text_for_db,
                        response,
                    )
                )
                save_task.add_done_callback(_log_save_error)

                def _log_compress_error(task):
                    try:
                        task.result()
                    except Exception as exc:
                        logger.warning(f"Background compress_history failed: {exc}")

                compress_task = _asyncio.ensure_future(
                    conv_service.compress_history(user_conversation_id)
                )
                compress_task.add_done_callback(_log_compress_error)

            if response:
                for char in response:
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': char}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Tutor chat SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '答疑失败，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/exercise/generate")
async def exercise_generate(body: ExerciseGenRequest):
    topic = body.topic.strip()
    count = body.count
    difficulty = body.difficulty
    student_profile = body.student_profileSoftware-Fighters-Project/ai-service/internal_api.py
    user_id = body.user_id

    if not student_profile:
        student_profile = await _load_profile(user_id)

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


@router.get("/path/{student_id}")
async def learning_path(student_id: str):
    workflow = _get_path_workflow()

    try:
        user_id = int(student_id)
    except (ValueError, TypeError):
        return api_error(ErrorCode.INVALID_REQUEST, f"student_id must be an integer, got: {student_id}")

    student_profile = await _load_profile(user_id)

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
        "resource_ids": state.get("resource_ids", []),
        "response": state.get("response", ""),
    })


@router.get("/profile/workflow/status")
async def profile_workflow_status(user_id: int = Query(default=1)):
    """查询画像完整度（供前端判断是否继续引导对话）"""
    workflow = _get_profile_workflow()
    profile = await _load_profile(user_id)
    status = workflow.check_profile_status(profile)
    return api_success(status)


@router.post("/resources/export-pptx")
async def export_pptx(body: ExportPptxRequest):
    """Export content blocks to PPTX file."""
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
    """Download a generated PPTX file by filename."""
    # Prevent path traversal
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


@router.post("/solve")
async def solve_question(body: SolveRequest):
    question = body.question.strip()
    context = body.context
    user_id = body.user_id

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
                for char in solution:
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': char}, ensure_ascii=False)}\n\n"

            confidence = state.get("confidence_score")
            if confidence is not None:
                yield f"data: {json.dumps({'type': 'confidence', 'score': confidence}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Solve SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': '解题功能暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/exercise/error-analysis")
async def exercise_error_analysis(body: ErrorAnalysisRequest):
    """对错题进行深度分析，解释错误原因和改进方法"""
    from app.utils.prompt_loader import load_prompt_file

    errors = body.errors
    level = body.level

    try:
        sys_prompt = load_prompt_file("tutor_agent", "error_analysis.yaml", key="system")
        user_tpl = load_prompt_file("tutor_agent", "error_analysis.yaml", key="user_template")
        from app.utils.prompt_loader import interpolate_variables

        user_prompt = interpolate_variables(
            user_tpl,
            {"errors": json.dumps(errors, ensure_ascii=False), "level": str(level)},
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


@router.post("/evaluation/report")
async def get_evaluation_report(body: EvaluationReportRequest):
    user_id = body.user_id
    evaluation_results = body.evaluation_results

    from app.services.evaluation_report import generate_report

    report = generate_report(evaluation_results)
    if user_id is not None:
        from app.services.profile_service import get_profile_service

        profile_service = get_profile_service()
        await profile_service.incremental_update(user_id, report)
    return api_success(report)


# ── GraphService singleton ───────────────────────────────────────

_graph_service_singleton = None


def _get_graph_service():
    global _graph_service_singleton
    if _graph_service_singleton is None:
        from app.services.graph_service import get_graph_service
        _graph_service_singleton = get_graph_service()
    return _graph_service_singleton


# ── Knowledge Graph Endpoints ────────────────────────────────────


@router.get("/knowledge-graph/{course_id}")
async def get_knowledge_graph(course_id: str, user_id: int = Query(default=1)):
    """获取完整知识图谱（含用户掌握度+颜色映射）"""
    try:
        graph_service = _get_graph_service()
        graph = await graph_service.get_graph(user_id, course_id)
        return api_success(graph)
    except Exception as e:
        logger.error(f"Failed to get knowledge graph: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "获取知识图谱失败", status_code=500)


@router.get("/knowledge-graph/{course_id}/node/{node_id}")
async def get_node_card(course_id: str, node_id: str, user_id: int = Query(default=1)):
    """获取节点卡片详情（基本信息+子概念掌握度+图谱上下文+推荐动作）"""
    try:
        graph_service = _get_graph_service()
        card = await graph_service.get_node_card(user_id, course_id, node_id)
        return api_success(card)
    except ValueError as e:
        return api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    except Exception as e:
        logger.error(f"Failed to get node card: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "获取节点卡片失败", status_code=500)


# ── Learning Plan Endpoints ──────────────────────────────────────


@router.post("/plans/create")
async def create_plan(body: PlanCreateRequest):
    """从路径规划结果创建学习计划"""
    from app.models.learning_plan import LearningPlan, PlanStep

    try:
        user_id = body.user_id
        course_id = body.course_id
        steps = body.steps
        concept_graph = body.concept_graph

        node_map = {}
        for node in concept_graph.get("nodes", []):
            node_map[node.get("name", "")] = node.get("id", "")
            node_map[node.get("label", "")] = node.get("id", "")

        async with get_db() as session:
            plan = LearningPlan(
                user_id=user_id,
                course_id=course_id,
                title=f"学习计划 - {course_id}",
                status="in_progress",
                total_steps=len(steps),
                completed_steps=0,
            )
            session.add(plan)
            await session.flush()

            for i, step in enumerate(steps):
                topic = step.get("topic", "")
                knowledge_node_id = node_map.get(topic, "")

                plan_step = PlanStep(
                    plan_id=plan.id,
                    step_order=i + 1,
                    topic=topic,
                    knowledge_node_id=knowledge_node_id,
                    status=step.get("status", "pending"),
                    estimated_days=step.get("estimated_days", 1),
                    topic_difficulty=3,
                )
                session.add(plan_step)

            await session.commit()
            return api_success({"plan_id": plan.id, "total_steps": len(steps)})
    except Exception as e:
        logger.error(f"Failed to create plan: {e}")
        return api_error(ErrorCode.PERSIST_FAILED, f"创建计划失败: {e}", status_code=500)


@router.get("/plans/{plan_id}/status")
async def get_plan_status(plan_id: int, user_id: int = Query(default=1)):
    """查询计划状态（含软着陆触发检测）"""
    from datetime import datetime, timezone
    from app.models.learning_plan import LearningPlan, PlanStep

    try:
        async with get_db() as session:
            result = await session.execute(
                select(LearningPlan).where(
                    LearningPlan.id == plan_id,
                    LearningPlan.user_id == user_id,
                )
            )
            plan = result.scalar_one_or_none()
            if not plan:
                return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

            steps_result = await session.execute(
                select(PlanStep)
                .where(PlanStep.plan_id == plan_id)
                .order_by(PlanStep.step_order)
            )
            steps = steps_result.scalars().all()

            days_idle = 0
            if plan.last_activity_at:
                now = datetime.now(timezone.utc)
                delta = now - plan.last_activity_at.replace(tzinfo=timezone.utc)
                days_idle = delta.days

            plan_service = get_plan_service()

            paused_steps = [s for s in steps if s.status in ("paused", "in_progress")]
            soft_landing = None
            if plan.status == "paused" and days_idle > 0:
                paused_dicts = [
                    {
                        "topic": s.topic,
                        "mastery_current": s.mastery_current or 0,
                        "topic_difficulty": s.topic_difficulty or 3,
                        "review_count": s.review_count or 0,
                    }
                    for s in paused_steps
                ]
                soft_landing = plan_service.soft_landing(paused_dicts, days_idle)
                soft_landing["days_idle"] = days_idle

            steps_data = []
            for s in steps:
                step_dict = {
                    "id": s.id,
                    "step_order": s.step_order,
                    "topic": s.topic,
                    "knowledge_node_id": s.knowledge_node_id,
                    "status": s.status,
                    "topic_difficulty": s.topic_difficulty,
                    "mastery_current": s.mastery_current,
                }
                if s.status in ("paused", "in_progress") and days_idle > 0:
                    decayed = plan_service.estimate_decay(
                        s.mastery_current or 0, days_idle,
                        s.topic_difficulty or 3, s.review_count or 0,
                    )
                    step_dict["decayed_mastery"] = decayed
                steps_data.append(step_dict)

            return api_success({
                "plan_id": plan.id,
                "user_id": plan.user_id,
                "status": plan.status,
                "total_steps": plan.total_steps,
                "completed_steps": plan.completed_steps,
                "days_idle": days_idle,
                "soft_landing": soft_landing,
                "steps": steps_data,
            })
    except Exception as e:
        logger.error(f"Failed to get plan status: {e}")
        return api_error(ErrorCode.INTERNAL_ERROR, "查询计划状态失败", status_code=500)


@router.post("/plans/{plan_id}/progress")
async def update_plan_progress(plan_id: int, body: PlanProgressRequest):
    """更新步骤进度 + 触发掌握度更新"""
    from datetime import datetime, timezone
    from app.models.learning_plan import LearningPlan, PlanStep
    from app.models.learning_activity import LearningActivity
    from app.models.node_mastery import NodeMastery

    try:
        user_id = body.user_id

        async with get_db() as session:
            result = await session.execute(
                select(LearningPlan).where(
                    LearningPlan.id == plan_id,
                    LearningPlan.user_id == user_id,
                )
            )
            plan = result.scalar_one_or_none()
            if not plan:
                return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

            plan.last_activity_at = datetime.now(timezone.utc)

            step_result = await session.execute(
                select(PlanStep).where(
                    PlanStep.id == body.step_id,
                    PlanStep.plan_id == plan_id,
                )
            )
            step = step_result.scalar_one_or_none()
            if not step:
                return api_error(ErrorCode.NOT_FOUND, "步骤不存在", status_code=404)

            plan_service = get_plan_service()

            if body.status:
                step.status = body.status

            current_mastery = step.mastery_current or 0
            activity_type = body.activity_type or "study"

            if activity_type in ("exercise", "quiz") and body.score is not None:
                if body.score >= 0.6:
                    new_mastery = plan_service.update_mastery(current_mastery, "exercise_done", body.score)
                else:
                    new_mastery = plan_service.update_mastery(current_mastery, "exercise_failed")
            elif activity_type in ("exercise", "quiz") and body.score is None:
                new_mastery = current_mastery
                logger.warning("exercise/quiz activity without score for step %s — mastery unchanged", body.step_id)
            else:
                new_mastery = plan_service.update_mastery(current_mastery, activity_type, body.score)

            step.mastery_after = new_mastery
            step.mastery_current = new_mastery
            step.review_count = (step.review_count or 0) + 1
            step.last_review_at = datetime.now(timezone.utc)

            if body.status == "completed":
                step.completed_at = datetime.now(timezone.utc)
                plan.completed_steps = min(
                    plan.completed_steps + 1, plan.total_steps or 0
                )

            activity = LearningActivity(
                user_id=user_id,
                plan_id=plan_id,
                step_id=body.step_id,
                activity_type=body.activity_type,
                duration_minutes=body.duration_minutes,
                score=body.score,
            )
            session.add(activity)

            if step.knowledge_node_id:
                mastery_stmt = select(NodeMastery).where(
                    NodeMastery.user_id == user_id,
                    NodeMastery.node_id == step.knowledge_node_id,
                )
                mastery_result = await session.execute(mastery_stmt)
                mastery = mastery_result.scalar_one_or_none()

                if mastery is None:
                    mastery = NodeMastery(
                        user_id=user_id,
                        node_id=step.knowledge_node_id,
                        course_id=plan.course_id or "ai_intro",
                        mastery=new_mastery,
                        review_count=1,
                        last_review_at=datetime.now(timezone.utc),
                    )
                    session.add(mastery)
                else:
                    prev_mastery = mastery.mastery or 0
                    mastery.mastery = plan_service.update_mastery(
                        prev_mastery, activity_type, body.score
                    )
                    mastery.review_count = (mastery.review_count or 0) + 1
                    mastery.last_review_at = datetime.now(timezone.utc)

            await session.commit()

            return api_success({
                "plan_id": plan_id,
                "step_id": body.step_id,
                "status": step.status,
                "completed_steps": plan.completed_steps,
            })
    except Exception as e:
        logger.error(f"Failed to update progress: {e}", exc_info=True)
        return api_error(ErrorCode.PERSIST_FAILED, "更新进度失败，请稍后重试", status_code=500)


@router.post("/plans/{plan_id}/resume")
async def resume_plan(plan_id: int, body: PlanResumeRequest):
    """中断后回归，触发软着陆检查"""
    from datetime import datetime, timezone
    from app.models.learning_plan import LearningPlan

    try:
        async with get_db() as session:
            result = await session.execute(
                select(LearningPlan).where(
                    LearningPlan.id == plan_id,
                    LearningPlan.user_id == body.user_id,
                )
            )
            plan = result.scalar_one_or_none()
            if not plan:
                return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

            plan.status = "in_progress"
            plan.paused_at = None
            plan.last_activity_at = datetime.now(timezone.utc)

            await session.commit()

            return api_success({
                "plan_id": plan.id,
                "status": plan.status,
                "message": "已恢复计划",
            })
    except Exception as e:
        logger.error(f"Failed to resume plan: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "恢复计划失败，请稍后重试", status_code=500)


# ── Regression Check Endpoint ────────────────────────────────────


@router.post("/plans/{plan_id}/regression-check")
async def regression_check(plan_id: int, body: RegressionCheckRequest):
    """回归检测管线：出题 → 判分 → 重排"""
    from datetime import datetime, timezone
    from app.models.learning_plan import LearningPlan, PlanStep

    try:
        plan_service = get_plan_service()

        async with get_db() as session:
            result = await session.execute(
                select(LearningPlan).where(
                    LearningPlan.id == plan_id,
                    LearningPlan.user_id == body.user_id,
                )
            )
            plan = result.scalar_one_or_none()
            if not plan:
                return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

            steps_result = await session.execute(
                select(PlanStep)
                .where(PlanStep.plan_id == plan_id)
                .order_by(PlanStep.step_order)
            )
            steps = list(steps_result.scalars().all())

            days_idle = 0
            if plan.last_activity_at:
                now = datetime.now(timezone.utc)
                delta = now - plan.last_activity_at.replace(tzinfo=timezone.utc)
                days_idle = delta.days

            paused_steps = [s for s in steps if s.status in ("paused", "in_progress")]

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
                    "topic": s.topic,
                    "mastery_current": s.mastery_current or 0,
                    "topic_difficulty": s.topic_difficulty or 3,
                    "review_count": s.review_count or 0,
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

        async with get_db() as session:
            steps_result2 = await session.execute(
                select(PlanStep)
                .where(PlanStep.plan_id == plan_id)
                .order_by(PlanStep.step_order)
            )
            steps = list(steps_result2.scalars().all())

            decay_results = {}
            for step in steps:
                if step.status in ("paused", "in_progress"):
                    decayed = plan_service.estimate_decay(
                        step.mastery_current or 0, days_idle,
                        step.topic_difficulty or 3, step.review_count or 0,
                    )
                    if decayed < 0.6:
                        decay_results[step.topic] = "review" if decayed < 0.3 else "review_light"

            answers_by_topic = {}
            for ans in body.answers:
                topic = ans.get("topic", "")
                answers_by_topic.setdefault(topic, []).append(ans)

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
                matched = [s for s in steps if s.topic == topic]
                for step in matched:
                    prev_mastery = step.mastery_current or 0
                    if avg_score >= 0.6:
                        step.mastery_current = plan_service.update_mastery(prev_mastery, "exercise_done", avg_score)
                    else:
                        step.mastery_current = plan_service.update_mastery(prev_mastery, "exercise_failed")
                    step.review_count = (step.review_count or 0) + 1
                    step.last_review_at = datetime.now(timezone.utc)

            if decay_results:
                current_node = steps[0].knowledge_node_id if steps else ""
                goal_node = steps[-1].knowledge_node_id if steps else ""
                step_dicts = [
                    {"topic": s.topic, "status": s.status, "step_order": s.step_order,
                     "knowledge_node_id": s.knowledge_node_id or "",
                     "mastery_current": s.mastery_current, "topic_difficulty": s.topic_difficulty}
                    for s in steps
                ]
                reordered = plan_service.reorder_plan(
                    step_dicts, decay_results, days_idle,
                    current_topic=current_node, goal_topic=goal_node,
                )

                topic_to_step = {s.topic: s for s in steps}
                new_order = 1
                for item in reordered:
                    topic = item.get("topic", "")
                    if topic in topic_to_step:
                        topic_to_step[topic].step_order = new_order
                        topic_to_step[topic].status = item.get("status", topic_to_step[topic].status)
                    else:
                        new_step = PlanStep(
                            plan_id=plan_id,
                            step_order=new_order,
                            topic=topic,
                            knowledge_node_id=item.get("knowledge_node_id", ""),
                            status=item.get("status", "review"),
                            topic_difficulty=3,
                            mastery_current=0.0,
                        )
                        session.add(new_step)
                        steps.append(new_step)
                    new_order += 1

                plan.total_steps = len(reordered)

            plan.status = "in_progress"
            plan.last_activity_at = datetime.now(timezone.utc)
            await session.commit()

        reordered_steps = sorted(steps, key=lambda s: s.step_order)
        return api_success({
            "plan_id": plan_id,
            "strategy": "regression_check",
            "message": RETURN_MESSAGES["after_pass"] if not decay_results else RETURN_MESSAGES["after_fail"],
            "questions": [],
            "reordered_steps": [
                {"step_order": s.step_order, "topic": s.topic, "status": s.status,
                 "mastery_current": s.mastery_current}
                for s in reordered_steps
            ],
        })

    except Exception as e:
        logger.error(f"Failed regression check: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "回归检测失败，请稍后重试", status_code=500)


# ── Review Schedule Endpoint ─────────────────────────────────────


@router.get("/plans/{plan_id}/review-schedule")
async def get_review_schedule(plan_id: int, user_id: int = Query(default=1),
                               days_ahead: int = Query(default=7, ge=1, le=30)):
    """获取未来 N 天的复习日程（间隔重复提醒）"""
    from app.models.learning_plan import LearningPlan, PlanStep

    try:
        async with get_db() as session:
            result = await session.execute(
                select(LearningPlan).where(
                    LearningPlan.id == plan_id,
                    LearningPlan.user_id == user_id,
                )
            )
            plan = result.scalar_one_or_none()
            if not plan:
                return api_error(ErrorCode.NOT_FOUND, "计划不存在", status_code=404)

            steps_result = await session.execute(
                select(PlanStep)
                .where(PlanStep.plan_id == plan_id)
                .order_by(PlanStep.step_order)
            )
            steps = steps_result.scalars().all()

        plan_service = get_plan_service()
        schedule = plan_service.get_review_schedule(steps, days_ahead)

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


# ── Node Status Change Endpoint ──────────────────────────────────


@router.post("/plans/{plan_id}/node-status-change")
async def on_node_status_change(plan_id: int, body: NodeStatusChangeRequest):
    """联动：知识图谱节点状态变化 → 计划重排"""
    try:
        plan_service = get_plan_service()
        result = await plan_service.on_node_status_change(
            user_id=body.user_id,
            node_id=body.node_id,
            old_status=body.old_status,
            new_status=body.new_status,
            plan_id=plan_id,
        )
        return api_success(result)
    except Exception as e:
        logger.error(f"Failed node status change: {e}", exc_info=True)
        return api_error(ErrorCode.INTERNAL_ERROR, "联动处理失败，请稍后重试", status_code=500)


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
    message = body.message.strip()
    user_id = body.user_id

    extractor = _get_intent_extractor()
    result = await extractor.extract(message)

    intent = result.intent
    params = result.params

    dispatch = {
        "exercise_gen": lambda: exercise_generate(ExerciseGenRequest(
            topic=params.get("topic", "AI基础"),
            count=params.get("count", 3),
            difficulty=params.get("difficulty", "medium"),
            user_id=user_id,
        )),
        "resource_gen": lambda: resources_generate(ResourceGenRequest(
            topic=params.get("topic", "AI基础"), user_id=user_id,
        )),
        "tutor_question": lambda: tutor_chat(TutorChatRequest(
            user_id=user_id, content=params.get("question", message),
        )),
        "learning_path": lambda: learning_path(str(user_id)),
        "solve_problem": lambda: solve_question(SolveRequest(
            question=params.get("question", message), user_id=user_id,
        )),
        "flashcard_gen": lambda: resources_generate(ResourceGenRequest(
            topic=params.get("topic", "AI基础"), user_id=user_id,
        )),
    }

    handler = dispatch.get(intent)
    if handler:
        return await handler()

    # 意图识别为 unknown —— 记录日志，以 tutor_chat 兜底（通用问答）
    logger.info("Unified chat: intent=unknown, falling back to tutor_chat. message=%s", message[:120])
    return await tutor_chat(TutorChatRequest(
        user_id=user_id,
        content=message,
        messages=[{"role": "user", "content": message}],
    ))
