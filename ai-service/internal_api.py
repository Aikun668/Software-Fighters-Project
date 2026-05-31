import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

from app.utils.sse_heartbeat import sse_heartbeat_generator
from app.api.errors import ErrorCode, api_error, api_success

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
async def profile_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")

    messages = body.get("messages")
    user_id = body.get("user_id", 1)

    if messages is None:
        return api_error(ErrorCode.INVALID_REQUEST, "缺少 messages 字段")
    if not isinstance(messages, list):
        return api_error(ErrorCode.INVALID_REQUEST, f"messages 必须是数组，当前类型: {type(messages).__name__}")
    if len(messages) == 0:
        return api_error(ErrorCode.INVALID_REQUEST, "messages 不能为空数组")

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
            yield f"data: {json.dumps({'type': 'error', 'content': f'画像对话失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/resources/generate")
async def resources_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")

    topic = body.get("topic", "").strip() if isinstance(body.get("topic"), str) else ""
    user_id = body.get("user_id", 1)
    student_profile = body.get("student_profile", {})

    if not topic:
        return api_error(ErrorCode.MISSING_REQUIRED_FIELD, "topic is required")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return api_error(ErrorCode.INVALID_REQUEST, "user_id must be an integer")
    if not isinstance(student_profile, dict):
        return api_error(ErrorCode.INVALID_REQUEST, "student_profile must be an object")

    if not student_profile:
        student_profile = await _load_profile(user_id)

    workflow = _get_resource_workflow()

    async def event_stream():
        try:
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'plan', 'content': f'正在分析「{topic}」的知识点结构...'}, ensure_ascii=False)}\n\n"

            state = await workflow.run({
                "user_id": user_id,
                "topic": topic,
                "student_profile": student_profile,
            })

            yield f"data: {json.dumps({'type': 'progress', 'stage': 'outline_done', 'content': '大纲生成完成，开始并行生成资源...'}, ensure_ascii=False)}\n\n"

            content_blocks = state.get("content_blocks", [])
            questions = state.get("questions", [])

            for i, block in enumerate(content_blocks):
                await asyncio.sleep(0.3)
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'generating', 'index': i + 1, 'total': len(content_blocks), 'block_type': block.get('type', 'section')}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_block', 'data': block}, ensure_ascii=False)}\n\n"

            if questions:
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'exercises', 'content': f'已生成 {len(questions)} 道练习题'}, ensure_ascii=False)}\n\n"

            resource_ids = state.get("resource_ids", [])
            error = state.get("error", "")
            yield f"data: {json.dumps({'type': 'done', 'content_blocks': content_blocks, 'questions': questions, 'resource_ids': resource_ids, 'response': state.get('response', ''), 'error': error}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Resources generate SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'资源生成失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/tutor/chat")
async def tutor_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")

    messages = body.get("messages")
    user_id = body.get("user_id", 1)
    student_profile = body.get("student_profile", {})

    if messages is None:
        return api_error(ErrorCode.INVALID_REQUEST, "缺少 messages 字段")
    if not isinstance(messages, list):
        return api_error(ErrorCode.INVALID_REQUEST, "messages 必须是数组")
    if len(messages) == 0:
        return api_error(ErrorCode.INVALID_REQUEST, "messages 不能为空数组")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return api_error(ErrorCode.INVALID_REQUEST, "user_id must be an integer")
    if not isinstance(student_profile, dict):
        return api_error(ErrorCode.INVALID_REQUEST, "student_profile must be an object")

    if not student_profile:
        student_profile = await _load_profile(user_id)

    agent = _get_tutor_agent()

    async def event_stream():
        try:
            state = await agent.run({
                "messages": messages,
                "user_id": user_id,
                "student_profile": student_profile,
            })

            response = state.get("response", "")
            if response:
                for char in response:
                    await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'type': 'token', 'content': char}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Tutor chat SSE error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'答疑失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_heartbeat_generator(event_stream()), media_type="text/event-stream")


@router.post("/exercise/generate")
async def exercise_generate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")

    topic = body.get("topic", "").strip() if isinstance(body.get("topic"), str) else ""
    count = body.get("count", 3)
    difficulty = body.get("difficulty", "medium")
    student_profile = body.get("student_profile", {})
    user_id = body.get("user_id", 1)

    if not topic:
        return api_error(ErrorCode.MISSING_REQUIRED_FIELD, "topic is required")
    if type(count) is not int or count < 1 or count > 20:
        return api_error(ErrorCode.INVALID_REQUEST, "count must be an integer between 1 and 20")
    ALLOWED_DIFFICULTY = {"easy", "medium", "hard"}
    if difficulty not in ALLOWED_DIFFICULTY:
        return api_error(
            ErrorCode.INVALID_REQUEST,
            f"difficulty must be one of: {sorted(ALLOWED_DIFFICULTY)}",
        )
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return api_error(ErrorCode.INVALID_REQUEST, "user_id must be an integer")
    if not isinstance(student_profile, dict):
        return api_error(ErrorCode.INVALID_REQUEST, "student_profile must be an object")

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
            yield f"data: {json.dumps({'type': 'error', 'content': f'题目生成失败: {str(e)}'}, ensure_ascii=False)}\n\n"
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
async def export_pptx(request: Request):
    """Export content blocks to PPTX file."""
    from app.utils.ppt_exporter import export_to_pptx

    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")
    content_blocks = body.get("content_blocks", [])
    title = body.get("title", "AI学习资源")
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
async def grade_exercise(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")
    q_type = body.get("type", "choice")
    from app.services.evaluation_service import grade_choice, grade_short_answer

    if q_type == "choice":
        user_answer = body.get("user_answer")
        correct_answer = body.get("correct_answer")
        if user_answer is None or correct_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD,
                "user_answer and correct_answer are required",
            )
        result = grade_choice(
            user_answer,
            correct_answer,
            body.get("choices", [])
        )
    elif q_type == "short_answer":
        user_answer = body.get("user_answer")
        if user_answer is None:
            return api_error(
                ErrorCode.MISSING_REQUIRED_FIELD, "user_answer is required"
            )
        result = await grade_short_answer(
            user_answer,
            body.get("reference_answer", ""),
            body.get("rubric", "")
        )
    else:
        return api_error(
            ErrorCode.INVALID_REQUEST, f"Unknown question type: {q_type}"
        )
    return api_success(result)


@router.post("/evaluation/report")
async def get_evaluation_report(request: Request):
    try:
        body = await request.json()
    except Exception:
        return api_error(ErrorCode.INVALID_REQUEST, "请求体必须是有效的 JSON")
    user_id = body.get("user_id")
    evaluation_results = body.get("evaluation_results", {})
    if not isinstance(evaluation_results, dict):
        return api_error(ErrorCode.INVALID_REQUEST, "evaluation_results must be an object")

    from app.services.evaluation_report import generate_report

    report = generate_report(evaluation_results)
    if user_id is not None:
        from app.services.profile_service import get_profile_service

        profile_service = get_profile_service()
        await profile_service.incremental_update(user_id, report)
    return api_success(report)
