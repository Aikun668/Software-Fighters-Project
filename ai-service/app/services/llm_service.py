"""
LLM Provider 策略模式

支持两种后端：
  - Spark WebSocket API (讯飞星火)
  - OpenAI 兼容 HTTP API (DeepSeek/Qwen/Ollama 等)

通过 LLM_PROVIDER 环境变量切换，Agent 层无感知。

Per-agent 模型选择：
  - ModelConfig: 单次 LLM 调用的参数集（model, temperature, max_tokens）
  - AgentModelProfile: 将 Agent 角色（default/plan/generate）映射到 ModelConfig
  - 预设 profiles: 开箱即用的 Director/Content/Exercise/Code/MindMap/Reading 配置
"""

import asyncio
import os
import json
import hmac
import hashlib
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from time import mktime
from typing import AsyncGenerator, Any
from urllib.parse import urlparse, urlencode
from wsgiref.handlers import format_date_time

import websockets
import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Per-Agent Model Configuration
# ═══════════════════════════════════════════════════════════════


@dataclass
class ModelConfig:
    """单次 LLM 调用的参数集。

    Attributes:
        model: 模型名称（空字符串 = 使用环境变量默认值）
        temperature: 生成温度 (0.0 = 确定性, 1.0 = 最高随机性)
        max_tokens: 最大输出 token 数
    """
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192


@dataclass
class AgentModelProfile:
    """将 Agent 逻辑角色映射到 ModelConfig。

    若某个角色为 None，BaseAgent._get_llm(role) 回退到 default。
    若整个 profile 为 None，Agent 使用 create_llm() 默认行为。
    """
    default: ModelConfig = field(default_factory=ModelConfig)
    plan: ModelConfig | None = None
    generate: ModelConfig | None = None

    def get(self, role: str) -> ModelConfig:
        if role == "plan" and self.plan is not None:
            return self.plan
        if role == "generate" and self.generate is not None:
            return self.generate
        return self.default


# ── 开箱即用的预设 Profiles ──────────────────────────────────

PROFILE_DIRECTOR = AgentModelProfile(
    default=ModelConfig(temperature=0.0, max_tokens=256),
)

PROFILE_CONTENT = AgentModelProfile(
    default=ModelConfig(temperature=0.7, max_tokens=8192),
    plan=ModelConfig(temperature=0.3, max_tokens=4096),
)

PROFILE_EXERCISE = AgentModelProfile(
    default=ModelConfig(temperature=0.7, max_tokens=4096),
    plan=ModelConfig(temperature=0.3, max_tokens=2048),
)

PROFILE_CODE = AgentModelProfile(
    default=ModelConfig(temperature=0.5, max_tokens=8192),
)

PROFILE_MINDMAP = AgentModelProfile(
    default=ModelConfig(temperature=0.6, max_tokens=4096),
)

PROFILE_READING = AgentModelProfile(
    default=ModelConfig(temperature=0.7, max_tokens=4096),
)

PROFILE_FLASHCARD = AgentModelProfile(
    default=ModelConfig(temperature=0.6, max_tokens=4096),
)

PROFILE_INTERACTIVE_DIAGRAM = AgentModelProfile(
    default=ModelConfig(temperature=0.5, max_tokens=8192),
)

PROFILE_PROJECT = AgentModelProfile(
    default=ModelConfig(temperature=0.7, max_tokens=4096),
)


# ═══════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════


_llm_service_singleton = None


def get_llm_service(use_mock: bool | None = None):
    global _llm_service_singleton
    if _llm_service_singleton is None:
        if use_mock is None:
            use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"
        _llm_service_singleton = create_llm(use_mock=use_mock)
    elif use_mock is not None and use_mock != _llm_service_singleton.use_mock:
        raise RuntimeError(
            f"get_llm_service already initialized with use_mock="
            f"{_llm_service_singleton.use_mock}, "
            f"but called with use_mock={use_mock}"
        )
    return _llm_service_singleton


def create_llm(
    temperature: float = 0.7,
    max_tokens: int = 8192,
    use_mock: bool = False,
    model: str | None = None,
) -> Any:
    """LLM Provider 工厂——根据 LLM_PROVIDER 环境变量选择后端。

    LLM_PROVIDER=spark   → SparkLLM (讯飞 WebSocket)
    LLM_PROVIDER=openai  → OpenAILLM (OpenAI 兼容 HTTP)

    Args:
        model: 模型名称，仅 OpenAI 后端使用。None 时使用 OPENAI_MODEL 环境变量。
    """
    provider = os.getenv("LLM_PROVIDER", "spark").lower()
    if provider == "openai":
        return OpenAILLM(
            temperature=temperature,
            max_tokens=max_tokens,
            use_mock=use_mock,
            model=model,
        )
    return SparkLLM(
        temperature=temperature,
        max_tokens=max_tokens,
        use_mock=use_mock,
    )


# ═══════════════════════════════════════════════════════════════
# Spark Provider (WebSocket)
# ═══════════════════════════════════════════════════════════════


class SparkLLM:
    """讯飞星火大模型 API 封装（WebSocket 协议）"""

    SPARK_WS_URL = "wss://spark-api.xf-yun.com/v4.0/chat"
    SPARK_DOMAIN = "4.0Ultra"

    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        use_mock: bool = False,
    ):
        self.app_id = os.getenv("SPARK_APP_ID", "")
        self.api_key = os.getenv("SPARK_API_KEY", "")
        self.api_secret = os.getenv("SPARK_API_SECRET", "")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_mock = use_mock

        if not use_mock and (
            not self.app_id or not self.api_key or not self.api_secret
        ):
            raise ValueError(
                "SPARK_APP_ID, SPARK_API_KEY, and SPARK_API_SECRET "
                "must be set in .env when use_mock=False"
            )

    # ── WebSocket auth ──────────────────────────────────────────

    def _build_ws_url(self) -> str:
        """构建带签名的 WebSocket 连接 URL"""
        url = urlparse(self.SPARK_WS_URL)
        host = url.netloc
        path = url.path

        # RFC 1123 时间戳（与官方 SDK 一致的 wsgiref 实现）
        date_str = format_date_time(mktime(datetime.now().timetuple()))

        # 签名原文
        signature_origin = (
            f"host: {host}\n"
            f"date: {date_str}\n"
            f"GET {path} HTTP/1.1"
        )

        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                signature_origin.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(
            authorization_origin.encode("utf-8")
        ).decode("utf-8")

        params = urlencode({
            "authorization": authorization,
            "date": date_str,
            "host": host,
        })

        return f"{self.SPARK_WS_URL}?{params}"

    def _build_request(self, messages: list[dict]) -> dict:
        """构建 WebSocket 请求帧"""
        return {
            "header": {"app_id": self.app_id},
            "parameter": {
                "chat": {
                    "domain": self.SPARK_DOMAIN,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                }
            },
            "payload": {
                "message": {
                    "text": messages,
                }
            },
        }

    # ── public API ──────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> str:
        """非流式对话，收集完整回复后返回"""
        if self.use_mock:
            return self._mock_response(messages)

        full_messages = self._build_messages(messages, system_prompt)
        ws_url = self._build_ws_url()
        request = self._build_request(full_messages)

        try:
            async with asyncio.timeout(120.0):
                async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30.0) as ws:
                    await ws.send(json.dumps(request))
                    full_text = ""
                    async for raw in ws:
                        data = json.loads(raw)
                        code = data.get("header", {}).get("code", 1)
                        if code != 0:
                            msg = data.get("header", {}).get("message", "unknown")
                            raise RuntimeError(f"Spark WebSocket error {code}: {msg}")
                        choices = (
                            data.get("payload", {})
                            .get("choices", {})
                            .get("text", [])
                        )
                        for choice in choices:
                            full_text += choice.get("content", "")
                        status = data.get("header", {}).get("status", 2)
                        if status == 2:
                            break
                    return full_text
        except asyncio.TimeoutError:
            logger.error("Spark WebSocket timeout after 120s")
            raise RuntimeError("Spark WebSocket timeout: LLM did not respond within 120s")
        except OSError as e:
            logger.error(f"Spark WebSocket OS error: {e}")
            raise RuntimeError(f"Spark WebSocket connection failed: {e}")
        except websockets.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed: {e}")
            raise RuntimeError(f"Spark WebSocket connection failed: {e}")

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式对话，逐 token 返回"""
        if self.use_mock:
            for token in self._mock_stream_response(messages):
                yield token
                await asyncio.sleep(0.05)
            return

        full_messages = self._build_messages(messages, system_prompt)
        ws_url = self._build_ws_url()
        request = self._build_request(full_messages)

        try:
            async with asyncio.timeout(120.0):
                async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, open_timeout=30.0) as ws:
                    await ws.send(json.dumps(request))
                    async for raw in ws:
                        data = json.loads(raw)
                        code = data.get("header", {}).get("code", 1)
                        if code != 0:
                            msg = data.get("header", {}).get("message", "unknown")
                            raise RuntimeError(f"Spark WebSocket error {code}: {msg}")
                        choices = (
                            data.get("payload", {})
                            .get("choices", {})
                            .get("text", [])
                        )
                        for choice in choices:
                            content = choice.get("content", "")
                            if content:
                                yield content
                        status = data.get("header", {}).get("status", 2)
                        if status == 2:
                            break
        except asyncio.TimeoutError:
            logger.error("Spark WebSocket stream timeout after 120s")
            raise RuntimeError("Spark WebSocket stream timeout: LLM did not respond within 120s")
        except OSError as e:
            logger.error(f"Spark WebSocket OS error: {e}")
            raise RuntimeError(f"Spark WebSocket connection failed: {e}")
        except websockets.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed: {e}")
            raise RuntimeError(f"Spark WebSocket connection failed: {e}")

    # ── internal helpers ────────────────────────────────────────

    def _build_messages(
        self, messages: list[dict], system_prompt: str
    ) -> list[dict]:
        """构建消息列表，在开头插入 system prompt"""
        if system_prompt:
            return [{"role": "system", "content": system_prompt}] + list(messages)
        return list(messages)

    def _mock_response(self, messages: list[dict]) -> str:
        """Mock 非流式回复（用于画像提取测试）"""
        return (
            '{"updates": {'
            '"knowledge_base": 30, '
            '"learning_goal": "掌握机器学习与深度学习基础", '
            '"interest_direction": ["机器学习"], '
            '"weak_points": ["数学基础薄弱"], '
            '"cognitive_style": null, '
            '"learning_pace": null'
            '}}'
        )

    def _mock_stream_response(self, messages: list[dict]) -> list[str]:
        """Mock 流式回复（用于对话测试）"""
        response = (
            "你好！很高兴和你交流。从你刚才的描述来看，"
            "你已经有一定的编程基础了，这对学习AI领域非常有帮助。"
            "能跟我说说，你对AI的哪个方向最感兴趣呢？"
            "比如是想做图像识别、自然语言处理，还是数据科学方面？"
        )
        return list(response)


# ═══════════════════════════════════════════════════════════════
# OpenAI Provider (HTTP REST)
# ═══════════════════════════════════════════════════════════════


class OpenAILLM:
    """OpenAI 兼容 HTTP API 封装（DeepSeek / Qwen / Ollama / LM Studio 等）"""

    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        use_mock: bool = False,
        model: str | None = None,
    ):
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_mock = use_mock

        if not use_mock and not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY must be set in .env when use_mock=False"
            )

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> str:
        if self.use_mock:
            return self._mock_response(messages)

        full_messages = self._build_messages(messages, system_prompt)
        url = f"{self.base_url}/chat/completions"

        try:
            async with asyncio.timeout(120.0):
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    resp = await client.post(
                        url,
                        json={
                            "model": self.model,
                            "messages": full_messages,
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "stream": False,
                        },
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI HTTP error {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"OpenAI HTTP error: {e}")
        except asyncio.TimeoutError:
            logger.error("OpenAI timeout after 120s")
            raise RuntimeError("OpenAI timeout: LLM did not respond within 120s")
        except OSError as e:
            logger.error(f"OpenAI connection error: {e}")
            raise RuntimeError(f"OpenAI connection failed: {e}")

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        if self.use_mock:
            for token in self._mock_stream_response(messages):
                yield token
                await asyncio.sleep(0.05)
            return

        full_messages = self._build_messages(messages, system_prompt)
        url = f"{self.base_url}/chat/completions"

        try:
            async with asyncio.timeout(120.0):
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    async with client.stream(
                        "POST",
                        url,
                        json={
                            "model": self.model,
                            "messages": full_messages,
                            "temperature": self.temperature,
                            "max_tokens": self.max_tokens,
                            "stream": True,
                        },
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                data = json.loads(chunk)
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI stream HTTP error {e.response.status_code}")
            raise RuntimeError(f"OpenAI HTTP error: {e}")
        except asyncio.TimeoutError:
            logger.error("OpenAI stream timeout after 120s")
            raise RuntimeError("OpenAI stream timeout")
        except OSError as e:
            logger.error(f"OpenAI stream connection error: {e}")
            raise RuntimeError(f"OpenAI connection failed: {e}")

    def _build_messages(
        self, messages: list[dict], system_prompt: str
    ) -> list[dict]:
        if system_prompt:
            return [{"role": "system", "content": system_prompt}] + list(messages)
        return list(messages)

    def _mock_response(self, messages: list[dict]) -> str:
        return (
            '{"updates": {'
            '"knowledge_base": 30, '
            '"learning_goal": "掌握机器学习与深度学习基础", '
            '"interest_direction": ["机器学习"], '
            '"weak_points": ["数学基础薄弱"], '
            '"cognitive_style": null, '
            '"learning_pace": null'
            '}}'
        )

    def _mock_stream_response(self, messages: list[dict]) -> list[str]:
        response = (
            "你好！很高兴和你交流。从你刚才的描述来看，"
            "你已经有一定的编程基础了，这对学习AI领域非常有帮助。"
            "能跟我说说，你对AI的哪个方向最感兴趣呢？"
        )
        return list(response)
