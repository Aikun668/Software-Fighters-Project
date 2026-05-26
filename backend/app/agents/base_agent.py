"""
BaseAgent -- 所有智能体的基类

参考 DeepTutor 的 BaseAgent 设计模式：
  - 统一的 LLM 配置管理
  - Prompt 从 YAML 文件加载（非硬编码）
  - 统一的流式和非流式 LLM 调用接口
  - 子类只需定义 system prompt 和 build_graph()
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

import yaml
from langgraph.graph import StateGraph

from app.services.llm_service import SparkLLM


class BaseAgent(ABC):
    """所有智能体的抽象基类"""

    def __init__(
        self,
        agent_name: str,
        module: str = "agents",
        language: str = "zh",
        config: dict[str, Any] | None = None,
    ):
        self.agent_name = agent_name
        self.module = module
        self.language = language
        self.config = config or {}
        self.system_prompt = self._load_prompt()
        self.llm = SparkLLM(system_prompt=self.system_prompt)
        self.logger = logging.getLogger(f"{module}.{agent_name}")

    def _load_prompt(self) -> str:
        """从 prompts/{agent_name}/system.yaml 加载系统提示词"""
        prompt_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "prompts", self.agent_name
        )
        prompt_path = os.path.join(prompt_dir, "system.yaml")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("system", "")
        except FileNotFoundError:
            self.logger.warning(f"Prompt not found: {prompt_path}")
            return ""

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """子类重写：定义 LangGraph 状态图"""
        raise NotImplementedError

    async def run(self, input_state: dict) -> dict:
        """执行智能体工作流"""
        graph = self.build_graph()
        return await graph.ainvoke(input_state)

    async def chat(self, messages: list[dict]) -> str:
        """非流式对话"""
        return await self.llm.chat(messages)

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式对话"""
        async for chunk in self.llm.chat_stream(messages):
            yield chunk
