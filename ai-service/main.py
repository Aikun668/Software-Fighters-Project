import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from internal_api import router as internal_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — Java 后端负责 DB 管理，Python 端无需建表
    logger.info("AI service started (Java 后端负责数据存储)")
    yield
    # shutdown


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    try:
        from app.services.java_api_client import get_java_client
        client = get_java_client()
        result = await client._get("/health")
        java_ok = result is not None
    except Exception:
        java_ok = False

    return {
        "status": "ok" if java_ok else "degraded",
        "java_api": "connected" if java_ok else "unreachable",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
