"""
BaseWorkflow — 多 Agent 编排工作流基类

借鉴 DeepTutor BaseCapability 协议化思路：
  - 统一 run() 入口 + 进度回调
  - 子类实现 _build_graph() 返回编译后的 LangGraph StateGraph
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from langgraph.graph import StateGraph

from app.agents.base_agent import current_emitter
from app.events.graph_stream import ainvoke_with_events, graph_stream_enabled
from app.events.stream import StreamEmitter, ProgressEventType



class BaseWorkflow(ABC):
    """所有工作流的抽象基类"""

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
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
        """执行工作流。

        P3-E（流式阶段 C5）：**图流默认开启** —— 执行走 `astream`，把每个节点完成发成
        统一事件（`node.completed`），并注入 `current_emitter`，使节点里嵌套调用的
        Agent（`agent.run()`）也把内层节点事件汇入同一条流。返回值与 `ainvoke` 等价
        （契约 `GS-A02`/`CS-A01`），设 `AI_SERVICE_GRAPH_STREAM=0` 可整条退回旧路径。

        P0 修复（契约 `CS-B04`~`CS-B06`）：事件源**优先复用上游注入的实例**（如
        `ChatTaskDispatcher` 的 run_emitter）。此前无条件 `StreamEmitter()` 会覆盖
        上游，导致本工作流的节点事件落入一个**无消费者的局部实例**、run_id 也与
        同请求不一致。现在：有上游 → 复用（同一 run_id、同一条流）；无上游 → 自建
        （独立调用场景，事件仅落本地日志）。`AI_SERVICE_GRAPH_STREAM=0` 仍是硬总闸：
        一律不注入、退回 `ainvoke` 纯路径。
        """
        if on_progress:
            await on_progress("start", f"[{self.__class__.__name__}] 开始执行")

        emitter: StreamEmitter | None = None
        if graph_stream_enabled():
            emitter = current_emitter.get() or StreamEmitter()
        seq_base = emitter.seq if emitter is not None else 0

        ctx_token = current_emitter.set(emitter)
        try:
            result = await ainvoke_with_events(self.graph, state, emitter=emitter)
        finally:
            current_emitter.reset(ctx_token)

        if emitter is not None:
            # 只统计**本次 run** 产生的图节点事件：复用上游事件源时，其中已有前序
            # task 的轨迹；`"node" in data` 为纵深防御（center 级事件已改用 `center.*`，
            # 见 `EM-B04`）。
            nodes = [
                event.data["node"] for event in emitter.events
                if event.type is ProgressEventType.NODE_COMPLETED
                and event.seq > seq_base
                and "node" in event.data
            ]
            self.logger.info(
                "workflow %s run %s: %d node event(s) %s",
                self.__class__.__name__, emitter.run_id, len(nodes), nodes,
            )

        if on_progress:
            await on_progress("done", f"[{self.__class__.__name__}] 执行完成")
        return result

    @staticmethod
    def _quality_check(content_blocks: list[dict], questions: list[dict]) -> tuple[bool, str]:
        """纯逻辑质量检查（无 LLM 调用）。

        Returns:
            (passed, feedback): passed=True 表示通过，feedback 为失败时的具体原因。
        """
        if not content_blocks or len(content_blocks) < 2:
            return False, "内容块过少（<2），请扩展各节内容，增加讲解深度和示例"

        has_section = any(b.get("type") == "section" for b in content_blocks)
        if not has_section:
            return False, "缺少核心讲解内容（section 块），请为课程主题补充基础概念讲解"

        if not questions or len(questions) == 0:
            return False, "缺少练习题，请为课程生成配套习题以巩固学习效果"

        return True, ""

    @staticmethod
    async def _emit_progress(on_progress, stage: str, message: str):
        """向回调发送进度事件（SSE 用）"""
        if on_progress:
            await on_progress(stage, message)
