import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    uvicorn.run(app, host="127.0.0.1", port=8001)
