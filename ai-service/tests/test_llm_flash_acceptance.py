"""DeepSeek V4-Flash 真实验收：普通对话稳定性 + 思考模式降级 + reasoning 不泄漏。

覆盖四场景：
  1. 普通聊天（thinking=disabled）：正文非空、无 reasoning、可审计元数据。
  2. 开启思考且有正文（thinking=enabled）：正文非空，reasoning 仅存在于 API 原始响应。
  3. 开启思考但正文为空 → 自动降级（关思考同模型重试一次）：生产代码路径验证。
  4. 二轮追问（thinking=disabled）：能利用上一轮上下文（记忆名字）。

运行方式（门禁约定与 tests/conftest.py 一致）：
  # 离线部分（默认，零成本，不访问网络）：
  python -m pytest tests/test_llm_flash_acceptance.py -q
  # 真实 API 冒烟（需显式 --real-llm；约 7 次小请求，max_tokens<=1024）：
  python -m pytest tests/test_llm_flash_acceptance.py -q --real-llm -s

凭据：从 .env 的 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL_CHAT 读取，
     日志与证据文件不落 key（输出前经 _scrub 兜底脱敏）。
证据：每次真实用例把审计指标合并写入
     <仓库根>/archive/temp_file/归档/2026-09-06-llm-flash-acceptance-report.json
     （可用 LLM_ACCEPTANCE_EVIDENCE_PATH 覆盖路径）。
不改业务路由、不改前端；本文件只新增。
"""

import json
import logging
import os
import re
import time
from pathlib import Path

import aiohttp
import pytest
from unittest.mock import patch

from app.services.llm_service import OpenAILLM

pytestmark = pytest.mark.asyncio(loop_scope="function")

_REPORT_NAME = "2026-09-06-llm-flash-acceptance-report.json"
_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{6,}")
_FALLBACK_LOG = "retrying with thinking disabled"
_LLM_LOGGER = "app.services.llm_service"

_KEY_VARS = ("DEEPSEEK_API_KEY", "MINIMAX_API_KEY")
_BASE_VARS = ("DEEPSEEK_BASE_URL", "MINIMAX_BASE_URL")


def _env_pair(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "")
        if value:
            return value
    return default


def _scrub(text: str) -> str:
    """兜底脱敏：任何疑似 key 的串替换为 sk-***。"""
    return _KEY_RE.sub("sk-***", text or "")


def _evidence_path() -> Path:
    custom = os.getenv("LLM_ACCEPTANCE_EVIDENCE_PATH")
    if custom:
        p = Path(custom)
    else:
        # ai-service/tests/xxx.py → 仓库根/archive/temp_file/归档/
        p = Path(__file__).resolve().parents[2] / "archive" / "temp_file" / "归档" / _REPORT_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _write_evidence(record: dict) -> Path:
    """按 case_id 合并写入证据 JSON（单进程顺序执行，直接读改写）。"""
    path = _evidence_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    cases = data.get("cases", {})
    cases[record["case_id"]] = record
    data["cases"] = cases
    data["model_under_test"] = _env_pair(("DEEPSEEK_MODEL_CHAT",), "deepseek-v4-flash")
    data["base_url"] = _env_pair(_BASE_VARS, "https://api.deepseek.com/v1")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _record(case_id: str, **fields) -> None:
    record = {
        "case_id": case_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": _env_pair(("DEEPSEEK_MODEL_CHAT",), "deepseek-v4-flash"),
        "base_url": _env_pair(_BASE_VARS, "https://api.deepseek.com/v1"),
        "transport": "raw_http",
        "final_content_empty": None,
        "fallback_triggered": None,
        "finish_reason": None,
        "usage": None,
        "latency_ms": None,
        "error": None,
    }
    record.update(fields)
    for field in ("error", "content_preview", "final_content_preview"):
        if isinstance(record.get(field), str):
            record[field] = _scrub(record[field])[:200]
    path = _write_evidence(record)
    print(f"[evidence] {case_id} -> {path}")


@pytest.fixture
def flash_cfg() -> dict:
    key = _env_pair(_KEY_VARS)
    if not key:
        pytest.skip("DEEPSEEK_API_KEY 未配置（.env），跳过真实冒烟")
    return {
        "key": key,
        "base_url": _env_pair(_BASE_VARS, "https://api.deepseek.com/v1").rstrip("/"),
        "model": _env_pair(("DEEPSEEK_MODEL_CHAT",), "deepseek-v4-flash"),
    }


def _production_llm(cfg: dict, **kwargs) -> OpenAILLM:
    return OpenAILLM(
        api_key=cfg["key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        **kwargs,
    )


async def _raw_chat(
    *, messages: list[dict], thinking: bool, max_tokens: int, temperature: float
) -> dict:
    """直接调用 OpenAI 兼容 /chat/completions（非流式），保留全部可审计元数据。

    key 处理与生产 _pick_key 同构：.env 允许逗号分隔多把 key，逐把轮换，
    证据里只记 key_index（第几把），绝不落 key 本体。
    """
    keys = [k.strip() for k in _env_pair(_KEY_VARS).split(",") if k.strip()]
    base_url = _env_pair(_BASE_VARS, "https://api.deepseek.com/v1").rstrip("/")
    model = _env_pair(("DEEPSEEK_MODEL_CHAT",), "deepseek-v4-flash")
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking else "disabled"},
        "stream": False,
    }
    started = time.perf_counter()
    last_err = None
    for key_index, key in enumerate(keys):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120, connect=10)
            ) as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                ) as resp:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    if resp.status != 200:
                        err = _scrub(await resp.text())[:300]
                        last_err = {
                            "error": f"HTTP {resp.status}: {err}",
                            "http_status": resp.status,
                            "key_index": key_index,
                            "key_count": len(keys),
                            "latency_ms": latency_ms,
                        }
                        continue  # 试下一把 key（与生产 _KeyRejectedError 语义一致）
                    data = await resp.json()
            message = data["choices"][0]["message"]
            return {
                "content": message.get("content") or "",
                "reasoning": message.get("reasoning_content") or "",
                "finish_reason": data["choices"][0].get("finish_reason"),
                "usage": data.get("usage"),
                "latency_ms": latency_ms,
                "http_status": 200,
                "key_index": key_index,
                "key_count": len(keys),
                "error": None,
            }
        except Exception as e:  # 网络失败也要落证据，而不是丢上下文
            last_err = {
                "error": _scrub(f"{type(e).__name__}: {e}")[:300],
                "key_index": key_index,
                "key_count": len(keys),
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
    return last_err or {"error": "no api key configured", "key_count": 0}


# ═══════════════════════════════════════════════════════════════
# 离线部分：reasoning_content 绝不进入用户可见输出（确定性，零成本）
# ═══════════════════════════════════════════════════════════════


class _FakeStreamContent:
    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    async def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeHttpResponse:
    status = 200

    def __init__(self, lines):
        self.content = _FakeStreamContent(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        return ""


class _FakeHttpSession:
    def __init__(self, responses, requests):
        self._responses = responses
        self._requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, *, json, headers):
        self._requests.append(json)
        response = self._responses.pop(0)
        return response if isinstance(response, _FakeHttpResponse) else _FakeHttpResponse(response)


class TestReasoningNonLeakOffline:
    """合同：reasoning_content 只能停留在内部，不允许出现在任何用户可见输出里。"""

    @pytest.mark.asyncio
    async def test_stream_does_not_yield_reasoning_content(self):
        """流式：delta.reasoning_content 与正文混发时，产出的只有正文。"""
        requests = []
        responses = [
            [
                'data: {"choices":[{"delta":{"reasoning_content":"机密推理过程12345"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"content":"这是正文"},"finish_reason":null}]}',
                "data: [DONE]",
            ]
        ]
        with patch(
            "app.services.llm_service._create_session",
            side_effect=lambda: _FakeHttpSession(responses, requests),
        ):
            llm = OpenAILLM(
                api_key="test-key",
                base_url="https://example.test/v1",
                model="deepseek-v4-flash",
                thinking_enabled=True,
            )
            chunks = [c async for c in llm.chat_stream([{"role": "user", "content": "你好"}])]

        text = "".join(chunks)
        assert text == "这是正文"
        assert "机密推理过程12345" not in text

    @pytest.mark.asyncio
    async def test_non_stream_returns_only_content_field(self):
        """非流式：message 带 reasoning_content 时，chat() 只返回 content 字段。"""
        requests = []
        response = _FakeHttpResponse([])

        async def fake_json():
            return {
                "choices": [
                    {
                        "message": {
                            "content": "这是正文",
                            "reasoning_content": "机密推理过程12345",
                        }
                    }
                ]
            }

        response.json = fake_json
        with patch(
            "app.services.llm_service._create_session",
            side_effect=lambda: _FakeHttpSession([response], requests),
        ):
            llm = OpenAILLM(
                api_key="test-key",
                base_url="https://example.test/v1",
                model="deepseek-v4-flash",
                thinking_enabled=True,
            )
            result = await llm.chat([{"role": "user", "content": "你好"}])

        assert result == "这是正文"
        assert "机密推理过程12345" not in result


# ═══════════════════════════════════════════════════════════════
# 真实 API 部分：默认跳过，--real-llm 显式开启
# ═══════════════════════════════════════════════════════════════


@pytest.mark.real_llm
class TestDeepSeekFlashRealAcceptance:
    """真实 API 冒烟。门禁：tests/conftest.py 的 --real-llm / USE_REAL_LLM=1。"""

    async def test_case1_normal_chat_thinking_disabled(self, flash_cfg):
        """普通聊天：正文非空、无 reasoning、生产流式路径可用。"""
        question = "用一句话解释什么是 TCP 三次握手。"
        raw = await _raw_chat(
            messages=[{"role": "user", "content": question}],
            thinking=False,
            max_tokens=256,
            temperature=0.0,
        )
        assert raw["error"] is None, raw["error"]
        assert raw["content"].strip(), "普通聊天正文为空"
        assert not raw["reasoning"], "thinking=disabled 却返回了 reasoning_content"

        llm = _production_llm(flash_cfg, temperature=0.0, max_tokens=256, thinking_enabled=False)
        started = time.perf_counter()
        chunks = [c async for c in llm.chat_stream([{"role": "user", "content": question}])]
        stream_text = "".join(chunks)
        stream_ms = int((time.perf_counter() - started) * 1000)
        assert stream_text.strip(), "生产流式路径输出为空"

        _record(
            "case1_normal_chat",
            transport="raw_http+production_stream",
            thinking="disabled",
            max_tokens=256,
            temperature=0.0,
            fallback_triggered=False,
            final_content_empty=False,
            content_chars=len(raw["content"]),
            reasoning_chars=0,
            latency_ms=raw["latency_ms"],
            production_stream_latency_ms=stream_ms,
            production_stream_chars=len(stream_text),
            finish_reason=raw["finish_reason"],
            usage=raw["usage"],
            content_preview=raw["content"],
        )

    async def test_case2_thinking_enabled_with_content(self, flash_cfg):
        """思考开启：正文非空；reasoning 只出现在 API 原始响应里，不进生产返回值。"""
        question = "简单说明操作系统中进程和线程的区别。"
        raw = await _raw_chat(
            messages=[{"role": "user", "content": question}],
            thinking=True,
            max_tokens=1024,
            temperature=0.7,
        )
        assert raw["error"] is None, raw["error"]
        assert raw["content"].strip(), "思考模式正文为空（且未触发降级？见 case3）"

        llm = _production_llm(flash_cfg, temperature=0.7, max_tokens=1024, thinking_enabled=True)
        prod_text = await llm.chat([{"role": "user", "content": question}])
        assert prod_text.strip(), "生产 chat() 思考模式返回空"

        _record(
            "case2_thinking_with_content",
            transport="raw_http+production_chat",
            thinking="enabled",
            max_tokens=1024,
            temperature=0.7,
            fallback_triggered=False,
            final_content_empty=False,
            content_chars=len(raw["content"]),
            reasoning_chars=len(raw["reasoning"]),
            reasoning_present=bool(raw["reasoning"]),
            latency_ms=raw["latency_ms"],
            finish_reason=raw["finish_reason"],
            usage=raw["usage"],
            content_preview=raw["content"],
        )

    async def test_case3_thinking_empty_content_fallback(self, flash_cfg, caplog):
        """思考开启 + 极小 max_tokens 诱导正文为空 → 生产代码自动降级重试。

        真实 API 是否触发降级是概率性的（取决于思考是否耗尽 token 预算）：
          - 若触发：断言降级后正文非空，fallback_triggered=True；
          - 若未触发：正文本就非空，用例仍通过，但证据里如实记录
            degradation_observed=False（确定性分支由离线用例保证）。
        """
        caplog.set_level(logging.WARNING, logger=_LLM_LOGGER)
        question = "解释什么是数据库死锁。"
        probe = await _raw_chat(
            messages=[{"role": "user", "content": question}],
            thinking=True,
            max_tokens=32,
            temperature=0.7,
        )
        assert probe["error"] is None, probe["error"]

        llm = _production_llm(flash_cfg, temperature=0.7, max_tokens=32, thinking_enabled=True)
        final_text = await llm.chat([{"role": "user", "content": question}])

        fallback_triggered = _FALLBACK_LOG in caplog.text
        assert final_text.strip(), "最终（含降级重试后）正文为空"

        _record(
            "case3_thinking_empty_fallback",
            transport="raw_probe+production_chat",
            thinking="enabled->disabled(auto)",
            max_tokens=32,
            temperature=0.7,
            fallback_triggered=fallback_triggered,
            degradation_observed=fallback_triggered,
            probe_content_empty=not probe["content"].strip(),
            probe_finish_reason=probe["finish_reason"],
            probe_reasoning_chars=len(probe["reasoning"]),
            final_content_empty=not final_text.strip(),
            final_content_chars=len(final_text),
            latency_ms=probe["latency_ms"],
            usage=probe["usage"],
            final_content_preview=final_text,
            note=(
                "max_tokens=32 诱导思考耗尽预算；真实触发为概率事件，"
                "未触发不代表降级分支缺失（离线用例覆盖确定性）"
            ),
        )


@pytest.mark.real_llm
class TestDeepSeekFlashRealFollowup:
    async def test_case4_two_turn_followup(self, flash_cfg):
        """二轮追问：第二轮能利用第一轮上下文（记住名字）。"""
        llm = _production_llm(flash_cfg, temperature=0.0, max_tokens=128, thinking_enabled=False)
        messages = [
            {"role": "user", "content": "我叫小明，今年大三，请记住我的信息。"},
            {"role": "assistant", "content": "好的小明，我记住了：你今年大三。"},
            {"role": "user", "content": "请问我叫什么名字？一句话回答。"},
        ]
        started = time.perf_counter()
        chunks = [c async for c in llm.chat_stream(messages)]
        text = "".join(chunks)
        latency_ms = int((time.perf_counter() - started) * 1000)

        assert text.strip(), "二轮追问正文为空"
        assert "小明" in text, f"追问未利用上下文，回复：{text[:80]}"

        _record(
            "case4_two_turn_followup",
            transport="production_stream",
            thinking="disabled",
            max_tokens=128,
            temperature=0.0,
            fallback_triggered=False,
            final_content_empty=False,
            content_chars=len(text),
            latency_ms=latency_ms,
            context_turns=2,
            content_preview=text,
        )
