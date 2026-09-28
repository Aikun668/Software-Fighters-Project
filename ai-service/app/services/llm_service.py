"""
LLM Provider 策略模式

唯一后端：OpenAI 兼容 HTTP API (MiniMax/Qwen/Ollama 等)。

Per-agent 模型选择：
  - ModelConfig: 单次 LLM 调用的参数集（model, temperature, max_tokens, thinking_enabled）
  - AgentModelProfile: 将 Agent 角色（default/plan/generate）映射到 ModelConfig
  - 预设 profiles: 开箱即用的 Director/Content/Exercise/Code/MindMap/Reading 配置
"""

import asyncio
import os
import random
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Any

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
        thinking_enabled: 是否启用模型思考模式（默认关闭，保证普通对话直接产出正文）
        api_key: API Key（空字符串 = 使用环境变量 DEEPSEEK_API_KEY）
        base_url: API Base URL（空字符串 = 使用环境变量 DEEPSEEK_BASE_URL）
    """
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    thinking_enabled: bool = False
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
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
    plan=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=4096,
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_EXERCISE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.7, max_tokens=4096,
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
    plan=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=2048,
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_CODE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.5, max_tokens=8192,
        thinking_enabled=True,
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
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

PROFILE_PROJECT = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.7, max_tokens=8192,
        thinking_enabled=True,
        api_key=_LLM_KEY, base_url=_LLM_BASE,
    ),
)

# ── Diagnose / Profile ────────────────────────────────────────

PROFILE_DIAGNOSE = AgentModelProfile(
    default=ModelConfig(
        model=_MODEL_REASONER, temperature=0.3, max_tokens=4096,
        thinking_enabled=True,
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


def _env_mock_flag() -> bool:
    """统一 mock 开关（**单一真源**，学习闭环化 P0-B 决策 2）。

    主开关 `AI_SERVICE_MOCK_LLM`；兼容别名 `USE_MOCK_LLM`（过渡期，任一为真即为真）。

    归一前是两套并存：`internal_api._get_mock_flag()` 只读前者、
    `get_llm_service()` 只读后者。归一后两个读取入口同源，老环境（只配了
    `USE_MOCK_LLM`）行为只增不减。
    """
    for name in ("AI_SERVICE_MOCK_LLM", "USE_MOCK_LLM"):
        if os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


_llm_service_singleton = None


def get_llm_service(use_mock: bool | None = None):
    global _llm_service_singleton
    if _llm_service_singleton is None:
        if use_mock is None:
            use_mock = _env_mock_flag()
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
    use_mock: bool | None = None,
    model: str | None = None,
    api_key: str = "",
    base_url: str = "",
    thinking_enabled: bool = False,
) -> Any:
    """LLM Provider 工厂——统一返回 OpenAI 兼容 HTTP 后端。

    Args:
        use_mock: `True`/`False` 显式指定（显式优先）；`None`（默认）时读统一
            环境开关 `_env_mock_flag()` —— 保证"未显式传参"的路径也能离线构造。
        model: 模型名称。None 时使用 MINIMAX_MODEL_CHAT 环境变量。
        api_key: 非空时优先于 MINIMAX_API_KEY 环境变量。
        base_url: 非空时优先于 MINIMAX_BASE_URL 环境变量。
    """
    if use_mock is None:
        use_mock = _env_mock_flag()
    return OpenAILLM(
        temperature=temperature,
        max_tokens=max_tokens,
        use_mock=use_mock,
        model=model,
        api_key=api_key,
        base_url=base_url,
        thinking_enabled=thinking_enabled,
    )


# ═══════════════════════════════════════════════════════════════
# OpenAI Provider (HTTP REST)
# ═══════════════════════════════════════════════════════════════


class OpenAILLM:
    """OpenAI 兼容 HTTP API 封装（MiniMax / Qwen / Ollama / LM Studio 等）"""

    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        use_mock: bool | None = None,
        model: str | None = None,
        api_key: str = "",
        base_url: str = "",
        thinking_enabled: bool = False,
    ):
        if use_mock is None:
            use_mock = _env_mock_flag()
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "") or os.getenv("MINIMAX_BASE_URL", "https://api.minimax.cn/v1")).rstrip("/")
        raw_key = api_key or os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("MINIMAX_API_KEY", "")
        self._all_keys = [k.strip() for k in raw_key.split(",") if k.strip()]
        self.api_key = _pick_key(raw_key)
        self.model = model or os.getenv("DEEPSEEK_MODEL_CHAT", "") or os.getenv("MINIMAX_MODEL_CHAT", "MiniMax-M3")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled
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
        retry_without_thinking = False
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
                                    "thinking": {"type": "enabled" if self.thinking_enabled else "disabled"},
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
                                content = data["choices"][0]["message"].get("content") or ""
                                if content or not self.thinking_enabled:
                                    return content
                                logger.warning(
                                    "LLM response ended without final content; "
                                    "retrying with thinking disabled (model=%s)",
                                    self.model,
                                )
                                retry_without_thinking = True
                    if retry_without_thinking:
                        break
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

        if retry_without_thinking:
            fallback_llm = OpenAILLM(
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                thinking_enabled=False,
            )
            return await fallback_llm.chat(messages, system_prompt)

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

        retry_without_thinking = False
        async with _llm_stream_semaphore:
            last_error = None
            for attempt in range(_MAX_RETRIES + len(keys)):
                key = keys[attempt % len(keys)]
                per_key_sem = await _acquire_per_key(key)
                reasoning_chars = 0
                final_content_chars = 0
                finish_reason = None
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
                                    "thinking": {"type": "enabled" if self.thinking_enabled else "disabled"},
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
                                        if final_content_chars:
                                            return
                                        if self.thinking_enabled:
                                            logger.warning(
                                                "LLM stream ended without final content; "
                                                "retrying with thinking disabled "
                                                "(model=%s, finish_reason=%s, reasoning_chars=%s)",
                                                self.model,
                                                finish_reason,
                                                reasoning_chars,
                                            )
                                            retry_without_thinking = True
                                            break
                                        logger.error(
                                            "LLM stream ended without content "
                                            "(model=%s, finish_reason=%s)",
                                            self.model,
                                            finish_reason,
                                        )
                                        raise RuntimeError("LLM empty final content")
                                    try:
                                        data = json.loads(chunk)
                                        choice = data["choices"][0]
                                        finish_reason = choice.get("finish_reason") or finish_reason
                                        delta = choice.get("delta", {})
                                        reasoning = delta.get("reasoning_content", "")
                                        reasoning_chars += len(reasoning or "")
                                        content = delta.get("content", "")
                                        if content:
                                            final_content_chars += len(content)
                                            yield content
                                    except (json.JSONDecodeError, KeyError, IndexError):
                                        continue
                                if retry_without_thinking:
                                    break
                    if retry_without_thinking:
                        break
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

            if not retry_without_thinking:
                raise RuntimeError(f"OpenAI stream failed with all keys: {last_error}")

        fallback_llm = OpenAILLM(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            thinking_enabled=False,
        )
        async for content in fallback_llm.chat_stream(messages, system_prompt):
            yield content

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
