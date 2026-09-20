import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from internal_api import router as internal_router
from app.api.errors import ErrorCode, api_error
from app.utils.security_middleware import SecurityMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — Java 后端负责 DB 管理，Python 端无需建表
    logger.info("AI service started (Java 后端负责数据存储)")
    yield
    # shutdown — 释放 LLM HTTP 连接池
    try:
        from app.services.llm_service import close_llm_clients
        await close_llm_clients()
    except Exception:
        pass


app = FastAPI(
    title="Software-Fighters AI Microservice",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "请求参数验证失败"
    loc = errors[0].get("loc", [])
    if loc:
        field = str(loc[-1]) if len(loc) > 1 else str(loc[0])
        msg = f"字段 '{field}' {msg}"
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """全局 500 兜底 —— 没有 try 的端点此前会漏出 FastAPI 默认的
    `text/plain: Internal Server Error`，前端按 success/errorCode 解析只能拿到空值。

    `Exception` 在 Starlette 里注册到最外层 ServerErrorMiddleware，只在异常
    逃过内层 ExceptionMiddleware 时才生效，因此 HTTPException 与
    RequestValidationError 的专属处理器语义不受影响；响应一旦开始发送
    （SSE 流中途出错）本处理器也不会补发第二个响应。
    """
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return api_error(ErrorCode.INTERNAL_ERROR, "服务内部错误，请稍后重试")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-inference"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
