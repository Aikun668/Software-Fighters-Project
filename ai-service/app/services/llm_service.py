"""
LLM Provider 策略模式

支持两种后端：
  - Spark WebSocket API (讯飞星火)
  - OpenAI 兼容 HTTP API (MiniMax/Qwen/Ollama 等)

通过 LLM_PROVIDER 环境变量切换，Agent 层无感知。

Per-agent 模型选择：
  - ModelConfig: 单次 LLM 调用的参数集（model, temperature, max_tokens）
  - AgentModelProfile: 将 Agent 角色（default/plan/generate）映射到 ModelConfig
  - 预设 profiles: 开箱即用的 Director/Content/Exercise/Code/MindMap/Reading 配置
"""

import asyncio
import os
import random
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
import aiohttp

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 并发控制
# ═══════════════════════════════════════════════════════════════

_MAX_CONCURRENT = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
_MAX_STREAM_CONCURRENT = int(os.getenv("LLM_MAX_STREAM_CONCURRENT", "20"))
_llm_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)           # chat() 专用
_llm_stream_semaphore = asyncio.Semaphore(_MAX_STREAM_CONCURRENT)  # chat_stream() 专用
_MAX_RETRIES = 1

# 每把 API key 的独立并发上限（防止单 key 被过度争抢导致限流）
_PER_KEY_MAX = int(os.getenv("LLM_PER_KEY_MAX", "2"))
_per_key_semaphores: dict[str, asyncio.Semaphore] = {}
_per_key_lock = asyncio.Lock()


async def _acquire_per_key(key: str) -> asyncio.Semaphore:
    """获取或创建单 key 限流信号量。"""
    if key not in _per_key_semaphores:
        async with _per_key_lock:
            if key not in _per_key_semaphores:
                _per_key_semaphores[key] = asyncio.Semaphore(_PER_KEY_MAX)
    return _per_key_semaphores[key]

def _pick_key(api_key: str) -> str:
    """多 key 负载分担：逗号分隔则随机选一把，单 key 原样返回。"""
    keys = [k.strip() for k in api_key.split(",") if k.strip()]
    if len(keys) <= 1:
        return api_key
    return random.choice(keys)


async def _aiter_lines_with_idle_timeout(resp, idle_timeout: float = 60.0):
    """包装 aiohttp 流式响应的行迭代，若 idle_timeout 秒内无新行则超时（默认 60s）。"""
    while True:
        try:
            async with asyncio.timeout(idle_timeout):
                line = await resp.content.readline()
            if not line:
                return
            yield line.decode("utf-8").rstrip("\r\n")
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"LLM stream idle timeout: no token received for {idle_timeout}s"
            )


class _KeyRejectedError(Exception):
    """内部异常：当前 API key 被拒绝（401/403/429），触发切换 key 重试。"""
    pass


def _create_session(timeout: float = 120.0, connect_timeout: float = 10.0) -> aiohttp.ClientSession:
    """创建 aiohttp session（每次请求新建，避免连接池复用问题）。"""
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout, connect=connect_timeout),
    )


async def close_llm_clients():
    """应用关闭时释放 LLM 连接资源。

    aiohttp 模式每次请求创建/销毁 session，无需显式清理。
    保留此函数以兼容 main.py 的生命周期调用。
    """
    logger.info("LLM HTTP clients cleanup (no-op for aiohttp)")


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
        api_key: API Key（空字符串 = 使用环境变量 DEEPSEEK_API_KEY）
        base_url: API Base URL（空字符串 = 使用环境变量 DEEPSEEK_BASE_URL）
    """
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    api_key: str = ""
    base_url: str = ""


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

# ── 环境变量速记（统一 LLM 直连；当前供应商：DeepSeek）────────
# 兼容回退：DEEPSEEK_API_KEY 缺失时回退旧 MINIMAX_API_KEY 变量
_LLM_KEY = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("MINIMAX_API_KEY", "")
_LLM_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
# 模型名集中管理：不在代码里散落供应商与模型名
_MODEL_CHAT = os.getenv("DEEPSEEK_MODEL_CHAT", "deepseek-v4-flash")
_MODEL_REASONER = os.getenv("DEEPSEEK_MODEL_REASONER", "") or _MODEL_CHAT

# ── 通道分配（两档）──────────────────────────────────────────
# chat     (MINIMAX_MODEL_CHAT)     : 路由 / 初筛 / 判断 / 画像 / 轻量生成
# reasoner (MINIMAX_MODEL_REASONER) : 重推理 + 代码 + 图解 + 项目 + 诊断

PROFILE_DIRECTOR = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.0, max_tokens=256,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_CONTENT = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.7, max_tokens=8192,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
    plan=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_EXERCISE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.7, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
    plan=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=2048,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_CODE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.5, max_tokens=8192,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_MINDMAP = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.6, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_READING = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.7, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_FLASHCARD = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.6, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_INTERACTIVE_DIAGRAM = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.5, max_tokens=8192,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_PROJECT = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.7, max_tokens=8192,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

# ── Diagnose / Profile ────────────────────────────────────────

PROFILE_DIAGNOSE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=4096,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_STUDENT = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.3, max_tokens=2048,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

# ── Visualize 管线专用 Profiles ──────────────────────────────

PROFILE_ANALYSIS = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.0, max_tokens=512,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_REVIEW = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_CHAT, temperature=0.0, max_tokens=1024,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
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
    api_key: str = "",
    base_url: str = "",
) -> Any:
    """LLM Provider 工厂——根据 LLM_PROVIDER 环境变量选择后端。

    LLM_PROVIDER=spark   → SparkLLM (讯飞 WebSocket)
    LLM_PROVIDER=openai  → OpenAILLM (OpenAI 兼容 HTTP)

    Args:
        model: 模型名称，仅 OpenAI 兼容后端使用。None 时使用 MINIMAX_MODEL_CHAT 环境变量。
        api_key: 非空时优先于 MINIMAX_API_KEY 环境变量。
        base_url: 非空时优先于 MINIMAX_BASE_URL 环境变量。
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        return OpenAILLM(
            temperature=temperature,
            max_tokens=max_tokens,
            use_mock=use_mock,
            model=model,
            api_key=api_key,
            base_url=base_url,
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

        last_error = None
        async with _llm_semaphore:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    async with asyncio.timeout(180.0):
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
                except (OSError, websockets.ConnectionClosed) as e:
                    last_error = e
                    if attempt < _MAX_RETRIES:
                        logger.warning(f"Spark WebSocket error (attempt {attempt+1}), retrying: {e}")
                        await asyncio.sleep(1.0)

        logger.error(f"Spark WebSocket connection failed after {_MAX_RETRIES+1} attempts: {last_error}")
        raise RuntimeError(f"Spark WebSocket connection failed: {last_error}")

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

        async with _llm_stream_semaphore:
            try:
                async with asyncio.timeout(180.0):
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
            except (OSError, websockets.ConnectionClosed) as e:
                logger.error(f"Spark WebSocket stream connection error: {e}")
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
    """OpenAI 兼容 HTTP API 封装（MiniMax / Qwen / Ollama / LM Studio 等）"""

    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        use_mock: bool = False,
        model: str | None = None,
        api_key: str = "",
        base_url: str = "",
    ):
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "") or os.getenv("MINIMAX_BASE_URL", "https://api.minimax.cn/v1")).rstrip("/")
        raw_key = api_key or os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("MINIMAX_API_KEY", "")
        self._all_keys = [k.strip() for k in raw_key.split(",") if k.strip()]
        self.api_key = _pick_key(raw_key)
        self.model = model or os.getenv("DEEPSEEK_MODEL_CHAT", "") or os.getenv("MINIMAX_MODEL_CHAT", "MiniMax-M3")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_mock = use_mock

        if not use_mock and not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY (或 MINIMAX_API_KEY) must be set in .env when use_mock=False"
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

        keys = self._all_keys.copy()
        random.shuffle(keys)
        if not keys:
            keys = [self.api_key]

        last_error = None
        async with _llm_semaphore:
            for attempt in range(_MAX_RETRIES + len(keys)):
                key = keys[attempt % len(keys)]
                per_key_sem = await _acquire_per_key(key)
                try:
                    async with asyncio.timeout(180.0), per_key_sem:
                        async with _create_session() as session:
                            async with session.post(
                                url,
                                json={
                                    "model": self.model,
                                    "messages": full_messages,
                                    "temperature": self.temperature,
                                    "max_tokens": self.max_tokens,
                                    "stream": False,
                                },
                                headers={
                                    "Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json",
                                },
                            ) as resp:
                                if resp.status != 200:
                                    err_text = await resp.text()
                                    if resp.status in (429, 401, 403) and len(keys) > 1:
                                        next_key = keys[(attempt + 1) % len(keys)]
                                        if next_key != key:
                                            logger.warning(f"Key rejected (HTTP {resp.status}), switching key")
                                            await asyncio.sleep(0.5)
                                            raise _KeyRejectedError(resp.status, err_text)
                                    raise RuntimeError(f"OpenAI HTTP error {resp.status}: {err_text[:200]}")
                                data = await resp.json()
                                return data["choices"][0]["message"]["content"]
                except _KeyRejectedError:
                    continue
                except asyncio.TimeoutError:
                    logger.error("OpenAI timeout after 120s")
                    raise RuntimeError("OpenAI timeout: LLM did not respond within 120s")
                except (aiohttp.ClientError, OSError) as e:
                    last_error = e
                    if attempt < _MAX_RETRIES + len(keys) - 1:
                        logger.warning(f"OpenAI network error (attempt {attempt+1}, key={key[:12]}...), retrying: {e}")
                        await asyncio.sleep(1.0)

        logger.error(f"OpenAI connection failed after {_MAX_RETRIES + len(keys)} attempts: {last_error}")
        raise RuntimeError(f"OpenAI connection failed: {last_error}")

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

        keys = self._all_keys.copy()
        random.shuffle(keys)
        if not keys:
            keys = [self.api_key]

        async with _llm_stream_semaphore:
            last_error = None
            for attempt in range(_MAX_RETRIES + len(keys)):
                key = keys[attempt % len(keys)]
                per_key_sem = await _acquire_per_key(key)
                try:
                    async with asyncio.timeout(180.0), per_key_sem:
                        async with _create_session() as session:
                            async with session.post(
                                url,
                                json={
                                    "model": self.model,
                                    "messages": full_messages,
                                    "temperature": self.temperature,
                                    "max_tokens": self.max_tokens,
                                    "stream": True,
                                },
                                headers={
                                    "Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json",
                                },
                            ) as resp:
                                if resp.status != 200:
                                    err_text = await resp.text()
                                    if resp.status in (429, 401, 403) and len(keys) > 1:
                                        next_key = keys[(attempt + 1) % len(keys)]
                                        if next_key != key:
                                            logger.warning(f"Stream key rejected (HTTP {resp.status}), switching key")
                                            await asyncio.sleep(0.5)
                                            raise _KeyRejectedError(resp.status, err_text)
                                    raise RuntimeError(f"OpenAI HTTP error {resp.status}: {err_text[:200]}")
                                async for line in _aiter_lines_with_idle_timeout(
                                    resp, idle_timeout=60.0
                                ):
                                    if not line.startswith("data: "):
                                        continue
                                    chunk = line[6:]
                                    if chunk == "[DONE]":
                                        return
                                    try:
                                        data = json.loads(chunk)
                                        delta = data["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                    except (json.JSONDecodeError, KeyError, IndexError):
                                        continue
                except _KeyRejectedError:
                    continue
                except asyncio.TimeoutError:
                    logger.error("OpenAI stream timeout after 180s")
                    raise RuntimeError("OpenAI stream timeout")
                except (aiohttp.ClientError, OSError) as e:
                    last_error = e
                    if attempt < _MAX_RETRIES + len(keys) - 1:
                        logger.warning(f"Stream connection error (attempt {attempt+1}), retrying: {e}")
                        await asyncio.sleep(0.5)
                        continue
                    logger.error(f"OpenAI stream connection error: {e}")
                    raise RuntimeError(f"OpenAI connection failed: {e}")

            raise RuntimeError(f"OpenAI stream failed with all keys: {last_error}")

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
