"""
讯飞星火大模型 API 封装

封装星火 Spark API，提供统一接口供所有 Agent 调用。
支持流式和非流式两种模式。

API 文档：https://www.xfyun.cn/doc/spark/Web.html
"""

import os
import json
import logging
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)


class SparkLLM:
    """讯飞星火大模型 API 封装"""

    SPARK_API_URL = "https://spark-api-open.xf-yun.com/v1/chat/completions"

    def __init__(
        self,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.api_key = os.getenv("SPARK_API_KEY", "")
        self.api_secret = os.getenv("SPARK_API_SECRET", "")
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def chat(self, messages: list[dict]) -> str:
        """非流式对话，返回完整回复"""
        full_messages = self._build_messages(messages)
        payload = self._build_payload(full_messages, stream=False)
        headers = self._build_headers()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.SPARK_API_URL, json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式对话，逐 token 返回"""
        full_messages = self._build_messages(messages)
        payload = self._build_payload(full_messages, stream=True)
        headers = self._build_headers()

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", self.SPARK_API_URL, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    def _build_messages(self, messages: list[dict]) -> list[dict]:
        """构建消息列表，自动添加 system prompt"""
        if self.system_prompt:
            return [{"role": "system", "content": self.system_prompt}] + list(messages)
        return list(messages)

    def _build_payload(self, messages: list[dict], stream: bool = False) -> dict:
        """构建请求体"""
        return {
            "model": "generalv3.5",
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    def _build_headers(self) -> dict:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
