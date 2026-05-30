import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+aiomysql://root:password@localhost:3306/ai_edu")

Base = declarative_base()

_engine = None
_async_session = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(DATABASE_URL, echo=False)
    return _engine


def _get_session():
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _async_session


def get_db() -> AsyncSession:
    """获取新的数据库 session（调用方负责用 async with 管理生命周期）"""
    return _get_session()()
