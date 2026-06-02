import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse

from app.utils.sse_heartbeat import sse_heartbeat_generator
from app.api.errors import ErrorCode, api_error, api_success
from app.api.models import (
    ProfileChatRequest,
    ResourceGenRequest,
    ExportPptxRequest,
    TutorChatRequest,
    ExerciseGenRequest,
    GradeRequest,
    EvaluationReportRequest,
)
from app.events.types import StreamEvent, done_event
from app.services.conversation_service import get_conversation_service

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


_MOCK_FLAG = os.getenv("USE_MOCK_LLM", "true").lower() == "true"


def _get_mock_flag() -> bool:
    return _MOCK_FLAG


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

    # ── 新 API：content + conversation_id ──
    if content is not None and content.strip():
        conv_service = get_conversation_service()
        conv = await conv_service.get_or_create_conversation(user_id, conversation_id)
        history = await conv_service.load_history(conv.id)
        messages = history + [{"role": "user", "content": content.strip()}]
        is_new_api = True
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

            # 持久化新消息（不阻塞流式输出）
            if is_new_api and response:
                import asyncio as _asyncio
                _asyncio.ensure_future(
                    conv_service.save_messages(
                        user_conversation_id,
                        content.strip(),
                        response,
                    )
                )

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
    student_profile = body.student_profile
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
