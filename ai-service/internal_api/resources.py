"""资源域路由：生成 + PPTX/DOCX/PDF 导出与下载。"""

import logging
import os
import time

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import (
    ExportDocxRequest,
    ExportPdfRequest,
    ExportPptxRequest,
    ResourceGenRequest,
)
from app.utils.prompt_guard import sanitize_model

logger = logging.getLogger("internal_api")

router = APIRouter()


@router.post("/resources/generate")
async def resources_generate(body: ResourceGenRequest):
    body = sanitize_model(body)
    topic = body.topic.strip()
    if not topic:
        return api.api_error(ErrorCode.INVALID_REQUEST, "topic 不能为空白", status_code=400)
    student_profile = body.student_profile
    resource_type = body.resource_type

    async def event_stream():
        async for event in api._get_resource_center().stream_generate(
            user_id=body.user_id,
            topic=topic,
            student_profile=student_profile,
            resource_type=resource_type or "",
        ):
            yield event.to_sse()

    return api.sse_response(event_stream())


@router.post("/resources/export-pptx")
async def export_pptx(body: ExportPptxRequest):
    from app.utils.ppt_exporter import export_to_pptx

    content_blocks = body.content_blocks
    title = body.title
    output_dir = api._EXPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.pptx")

    try:
        result_path = export_to_pptx(content_blocks, output_path, title)
    except Exception as e:
        logger.error(f"PPTX export failed: {e}", exc_info=True)
        return api.api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api.api_success({"filename": os.path.basename(result_path)})


@router.get("/resources/download-pptx")
async def download_pptx(filename: str = Query(...)):
    try:
        file_path = api.safe_export_path(filename, allowed_ext=".pptx", exports_dir=api._EXPORTS_DIR)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except FileNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=os.path.basename(file_path),
    )


# ── DOCX Export / Download ────────────────────────────────────

@router.post("/resources/export-docx")
async def export_docx(body: ExportDocxRequest):
    from app.utils.docx_exporter import export_to_docx

    content_blocks = body.content_blocks
    title = body.title
    sub_type = body.sub_type
    output_dir = api._EXPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.docx")

    try:
        result_path = export_to_docx(content_blocks, output_path, title, sub_type)
    except Exception as e:
        logger.error(f"DOCX export failed: {e}", exc_info=True)
        return api.api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api.api_success({"filename": os.path.basename(result_path)})


@router.get("/resources/download-docx")
async def download_docx(filename: str = Query(...)):
    try:
        file_path = api.safe_export_path(filename, allowed_ext=".docx", exports_dir=api._EXPORTS_DIR)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except FileNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(file_path),
    )


# ── PDF Export / Download ──────────────────────────────────────

@router.post("/resources/export-pdf")
async def export_pdf(body: ExportPdfRequest):
    from app.utils.pdf_exporter import export_to_pdf

    content_blocks = body.content_blocks
    title = body.title
    output_dir = api._EXPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"export_{int(time.time())}.pdf")

    try:
        result_path = export_to_pdf(content_blocks, output_path, title)
    except Exception as e:
        logger.error(f"PDF export failed: {e}", exc_info=True)
        return api.api_error(
            ErrorCode.GENERATION_FAILED, "导出失败，请稍后重试", status_code=500
        )
    return api.api_success({"filename": os.path.basename(result_path)})


@router.get("/resources/download-pdf")
async def download_pdf(filename: str = Query(...)):
    try:
        file_path = api.safe_export_path(filename, allowed_ext=".pdf", exports_dir=api._EXPORTS_DIR)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except FileNotFoundError as e:
        return api.api_error(ErrorCode.NOT_FOUND, str(e), status_code=404)
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path),
    )
