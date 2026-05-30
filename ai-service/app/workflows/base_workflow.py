"""
BaseWorkflow — 多 Agent 编排工作流基类

借鉴 DeepTutor BaseCapability 协议化思路：
  - 统一 run() 入口 + 进度回调
  - 复用 profile_service / knowledge_base 单例
  - 子类实现 _build_graph() 返回编译后的 LangGraph StateGraph
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from langgraph.graph import StateGraph

from app.services.profile_service import get_profile_service
from app.services.knowledge_base import get_kb


class BaseWorkflow(ABC):
    """所有工作流的抽象基类"""

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.profile_service = get_profile_service()
        self.kb = get_kb()
        self.logger = logging.getLogger(f"workflows.{self.__class__.__name__}")
        self._compiled_graph = None

    @abstractmethod
    def _build_graph(self) -> StateGraph:
        """子类实现：构建并返回编译后的 LangGraph StateGraph"""
        raise NotImplementedError

    @property
    def graph(self):
        """懒加载编译后的 StateGraph（延迟到子类 __init__ 完成后再构建）"""
        if self._compiled_graph is None:
            self._compiled_graph = self._build_graph()
        return self._compiled_graph

    async def run(self, state: dict, on_progress=None) -> dict:
        """执行工作流，通过编译后的图运行"""
        if on_progress:
            await on_progress("start", f"[{self.__class__.__name__}] 开始执行")
        result = await self.graph.ainvoke(state)
        if on_progress:
            await on_progress("done", f"[{self.__class__.__name__}] 执行完成")
        return result

    async def _load_profile(self, user_id: int) -> dict:
        """从 DB 加载学生画像，失败返回空 dict"""
        profile = await self.profile_service.get_profile(user_id)
        return profile or {}

    @staticmethod
    async def _emit_progress(on_progress, stage: str, message: str):
        """向回调发送进度事件（SSE 用）"""
        if on_progress:
            await on_progress(stage, message)
