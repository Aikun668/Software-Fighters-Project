"""评测域路由：`/eval/judge`（独立 LLM 裁判，绕过 Agent 包装）。"""

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

import internal_api as api
from app.api.errors import ErrorCode

logger = logging.getLogger("internal_api")

router = APIRouter()


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
        return api.api_error(ErrorCode.INVALID_REQUEST, "评测端点未启用", status_code=403)
    try:
        from app.services.llm_service import get_llm_service as _get_llm

        llm = _get_llm()
        messages = [{"role": "user", "content": body.message}]
        raw = await llm.chat(messages, system_prompt=body.system_prompt or "")
        return api.api_success({"response": raw})
    except Exception as e:
        logger.error(f"Eval judge failed: {e}", exc_info=True)
        # 不回显异常原文：上游报错里可能带内部路径、key 片段或 prompt 内容。
        return api.api_error(ErrorCode.INTERNAL_ERROR, "裁判调用失败，请稍后重试", status_code=500)
