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
    # startup
    from app.db.database import Base, _get_engine
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created (if not exist)")
    except Exception as e:
        logger.warning(f"Failed to create tables: {e}")

    yield

    # shutdown (预留，可在此关闭数据库连接池)


app = FastAPI(
    title="Software-Fighters AI Microservice",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """将 Pydantic 422 验证错误转为统一的 400 格式"""
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
    from sqlalchemy import text
    from app.db.database import _get_engine
    engine = _get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        return {"status": "degraded", "db": "unreachable"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, limit_max_size=20_000_000)  # 20MB for image uploads
