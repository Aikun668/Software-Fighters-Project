"""
BaseAgent -- 所有智能体的基类

参考 DeepTutor 的 BaseAgent 设计模式：
  - 统一的 LLM 配置管理
  - Prompt 从 YAML 文件加载（非硬编码）
  - 统一的流式和非流式 LLM 调用接口
  - 子类只需定义 system prompt 和 build_graph()

借鉴 OpenMAIC 的 buildPipeline：
  - {{snippet:name}} 片段复用
  - {{#if flag}}...{{/if}} 条件块
  - {variable} 变量插值
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from langgraph.graph import StateGraph

from app.services.llm_service import create_llm
from app.utils.prompt_loader import build_prompt


class BaseAgent(ABC):
    """所有智能体的抽象基类"""

    def __init__(
        self,
        agent_name: str,
        module: str = "agents",
        language: str = "zh",
        config: dict[str, Any] | None = None,
        use_mock_llm: bool = False,
    ):
        self.agent_name = agent_name
        self.module = module
        self.language = language
        self.config = config or {}
        self.use_mock_llm = use_mock_llm
        self.system_prompt = self._load_prompt()
        self.llm = create_llm(use_mock=use_mock_llm)
        self.logger = logging.getLogger(f"{module}.{agent_name}")
        self._compiled_graph = self.build_graph()

    def _load_prompt(
        self,
        filename: str = "system.yaml",
        variables: dict | None = None,
        key: str = "system",
    ) -> str:
        """加载 prompt 文件，支持 snippet / conditional / variable"""
        return build_prompt(
            self.agent_name,
            filename=filename,
            variables=variables,
            key=key,
        )

    def _load_extra_prompt(
        self,
        filename: str,
        variables: dict | None = None,
        key: str = "system",
    ) -> str:
        """加载额外的 prompt 文件（如 extract.yaml）"""
        return self._load_prompt(filename=filename, variables=variables, key=key)

    @abstractmethod
    def build_graph(self) -> "CompiledStateGraph":
        """子类重写：定义 LangGraph 状态图"""
        raise NotImplementedError

    async def run(self, input_state: dict) -> dict:
        """执行智能体工作流（使用缓存的 compiled graph）"""
        return await self._compiled_graph.ainvoke(input_state)

    async def chat(self, messages: list[dict]) -> str:
        """非流式对话"""
        return await self.llm.chat(messages, system_prompt=self.system_prompt)

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式对话"""
        async for chunk in self.llm.chat_stream(
            messages, system_prompt=self.system_prompt
        ):
            yield chunk

    @staticmethod
    def _format_profile(profile: dict) -> str:
        if not profile:
            return "（暂无学生画像，按默认难度生成）"
        lines = []
        labels = {
            "knowledge_base": "知识基础",
            "cognitive_style": "学习风格",
            "learning_goal": "学习目标",
            "weak_points": "薄弱环节",
            "learning_pace": "学习节奏",
            "interest_direction": "兴趣方向",
        }
        for key, label in labels.items():
            val = profile.get(key)
            if val is not None and val != []:
                if isinstance(val, list):
                    val = "、".join(str(v) for v in val)
                elif key == "knowledge_base":
                    val = f"{val}/100"
                lines.append(f"  - {label}: {val}")
        return "\n".join(lines) if lines else "（暂无学生画像，按默认难度生成）"

    async def _call_llm_json(
        self,
        system_prompt: str,
        user_prompt: str,
        expected_key: str | None = None,
        fallback: Any = None,
        max_retries: int = 1,
    ) -> Any:
        """
        调用 LLM 并解析 JSON 返回。
        流程：加载 prompt → 调 LLM → 解析 JSON → 校验字段 → 重试 → fallback
        """
        if fallback is None:
            fallback = {}

        from app.utils.json_parser import parse_llm_json

        messages = [{"role": "user", "content": user_prompt}]

        for attempt in range(max_retries + 1):
            try:
                result_text = await self.llm.chat(messages, system_prompt=system_prompt)
                result = parse_llm_json(result_text, fallback=fallback, expected_key=expected_key)
                if result != fallback:
                    return result
                if attempt < max_retries:
                    self.logger.warning(f"LLM JSON parse returned fallback, retrying ({attempt + 1}/{max_retries})")
            except (RuntimeError, ConnectionError) as e:
                self.logger.error(f"LLM call failed: {e}")
                if attempt < max_retries:
                    self.logger.info(f"Retrying LLM call ({attempt + 1}/{max_retries})")

        self.logger.error("All LLM JSON attempts failed, returning fallback")
        return fallback
