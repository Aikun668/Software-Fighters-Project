"""SSE 伪造帧注入契约 —— `sse_sanitize` 接线决策的前置证据。

背景：`app/utils/sse_response.sse_sanitize`（自 `e8a325e` 安全加固轮引入）在生产代码里
**零调用**。它自己的 docstring 写明：接线方式「需要先补『恶意换行 / 伪造 SSE 帧』
契约测试再决定」—— 本文件就是那个前置。

本文件先回答「威胁到底存不存在」，再据此锁定结论：

**Part A（FG-A01..A03）真实 ASGI 注入**
  恶意内容里塞 `\\n\\ndata: {"type":"done"}`：若帧可被伪造，客户端会看到一个**假的 done**
  → 流被提前截断（比"多一个 token"严重得多）。断言：帧数守恒、done 唯一、**每帧单行**。

**Part B（FG-B01..B02）帧构建必须 JSON 编码**
  这才是真正的防护：`json.dumps` 把真实换行转义成 `\\n`（反斜杠 + n 两个字符），
  内容里的换行**永远变不成帧分隔符**。本组用 AST 锁死这条不变量，防未来有人写出裸帧。

**Part C（FG-C01..C02）`sse_sanitize` 不得接线的机器化依据**
  - 帧层接线：帧结束符本身就是 `\\n\\n`，`sse_sanitize` 会把它吃掉 → **直接破坏协议**；
  - 内容层接线：`a\\n\\nb` → `a  b` → **markdown 空行消失**，属可见的产品退化；
  - 而在 JSON 编码已到位的前提下，它换不来任何安全增量。

> 结论：本文件**不主张接线**，而是把「为什么不该接」变成会红的断言；
> 既有「未接线锁」`SSE-D17` / `ERR-B06` 继续有效，并被本文件的证据支撑。
"""

import ast
import json
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from app.events.types import done_event, token_event

AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = AI_SERVICE_DIR / "app"
INTERNAL_API_DIR = AI_SERVICE_DIR / "internal_api"

DATA_PREFIX = "data: "

# 恶意载荷：两个 `\n\n` = 两次「伪造帧」机会；第二个 `data:` 伪造一个 token，
# 第一个伪造一个 **done**（能让任何按 done 收敛的客户端提前收流）。
EVIL_CONTENT = (
    '前半段\n\ndata: {"type": "done", "evil": true}\n\n'
    'data: {"type": "token", "content": "伪造"}\n\n后半段'
)


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
        )

    app.include_router(internal_api.router)
    return app


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        yield client


class CenterStub:
    """`stream_chat(**kwargs)` → 预置事件序列的异步生成器。"""

    def __init__(self, events):
        self._events = list(events)

    async def stream_chat(self, **kwargs):
        for event in self._events:
            yield event


def _frames(text: str) -> list[str]:
    """按 SSE 帧分隔符切分（丢弃空块）。"""
    return [block for block in text.split("\n\n") if block]


def _payload(frame: str) -> dict:
    assert frame.startswith(DATA_PREFIX), f"非法帧（不以 data: 开头）：{frame!r}"
    return json.loads(frame[len(DATA_PREFIX):])


def _install_tutor(monkeypatch, events):
    monkeypatch.setattr(internal_api, "_get_tutor_center", lambda: CenterStub(events))


TUTOR_BODY = {"user_id": 1, "messages": [{"role": "user", "content": "什么是进程"}]}


# ═══════════════════════════════════════════════════════════════════
# Part A —— 真实 ASGI 注入
# ═══════════════════════════════════════════════════════════════════


class TestForgedFrameInjection:

    @pytest.mark.asyncio
    async def test_fg_a01_forged_done_does_not_create_extra_frame(
        self, async_client, monkeypatch,
    ):
        """注入 `\\n\\ndata: {...done...}`：不得多出帧，done 仍唯一。"""
        _install_tutor(monkeypatch, [
            token_event(EVIL_CONTENT),
            done_event({"summary": "ok"}),
        ])

        response = await async_client.post("/internal/tutor/chat", json=TUTOR_BODY)

        frames = _frames(response.text)
        assert len(frames) == 2, f"帧数被注入改变：{len(frames)}\n{response.text!r}"

        types = [_payload(f)["type"] for f in frames]
        assert types == ["token", "done"], f"业务事件序列被污染：{types}"
        assert types.count("done") == 1, "出现了伪造的第二个 done"

    @pytest.mark.asyncio
    async def test_fg_a02_every_frame_is_single_line(self, async_client, monkeypatch):
        """结构不变量：每帧**单行**（换行必须已被转义）。"""
        _install_tutor(monkeypatch, [
            token_event(EVIL_CONTENT),
            done_event({"summary": "ok"}),
        ])

        response = await async_client.post("/internal/tutor/chat", json=TUTOR_BODY)

        for frame in _frames(response.text):
            assert "\n" not in frame, (
                "帧内出现裸换行 —— JSON 编码未生效，注入可行：\n" + frame
            )
            assert frame.startswith(DATA_PREFIX)

    @pytest.mark.asyncio
    async def test_fg_a03_content_survives_escaped_and_cr_is_neutralized(
        self, async_client, monkeypatch,
    ):
        """内容零丢失（只被转义）；`\\r` 不出现在原始响应字节里。"""
        evil_cr = "带回车\r的内容\r\rdata: {\"type\": \"done\"}"
        _install_tutor(monkeypatch, [
            token_event(EVIL_CONTENT),
            token_event(evil_cr),
            done_event({"summary": "ok"}),
        ])

        response = await async_client.post("/internal/tutor/chat", json=TUTOR_BODY)

        frames = _frames(response.text)
        assert len(frames) == 3, f"三帧（token/token/done）应恒为 3，实得 {len(frames)}"

        # 内容逐字保留（解码后与注入原文相同）
        assert _payload(frames[0])["content"] == EVIL_CONTENT
        assert _payload(frames[1])["content"] == evil_cr

        # 裸 CR 不得出现在响应字节里（否则部分客户端会把它当换行）
        assert "\r" not in response.text, "裸 CR 泄漏到响应字节"


# ═══════════════════════════════════════════════════════════════════
# Part B —— 帧构建必须 JSON 编码（真正的防护）
# ═══════════════════════════════════════════════════════════════════


def _sse_frame_fstrings(path: Path) -> list[tuple[int, str]]:
    """返回文件内所有「看起来在拼 SSE 帧」的表达式（行号, 源码）。

    覆盖两种写法：f-string（`f"data: {x}\\n\\n"`）与字符串拼接（`"data: " + x`）。
    纯静态常量帧（如心跳/边界兜底消息）不在扫描面内 —— 它们没有插值，无注入面。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        is_frame_shape = isinstance(node, ast.JoinedStr) or (
            isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
        )
        if not is_frame_shape:
            continue
        source = ast.unparse(node)
        if "data: " in source:
            found.append((node.lineno, source))
    return found


def _production_python_files() -> list[Path]:
    files = [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]
    files += [p for p in INTERNAL_API_DIR.rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(files)


class TestFrameConstruction:

    def test_fg_b01_every_sse_frame_template_json_encodes_its_payload(self):
        """任何 `f"data: ..."` 帧模板都必须经 `json.dumps` 编码载荷。"""
        offenders: list[str] = []
        scanned = 0
        for path in _production_python_files():
            for lineno, source in _sse_frame_fstrings(path):
                scanned += 1
                if "json.dumps" not in source:
                    offenders.append(
                        f"{path.relative_to(AI_SERVICE_DIR).as_posix()}:{lineno} → {source}"
                    )
        assert scanned > 0, "未扫描到任何 SSE 帧模板 —— 扫描逻辑失效"
        assert offenders == [], (
            "存在未 JSON 编码的 SSE 帧（注入通道）：\n" + "\n".join(offenders)
        )

    def test_fg_b02_event_to_sse_still_json_encodes(self):
        """锚点：`StreamEvent.to_sse()` 仍是 `json.dumps` 实现 + 内容换行被转义。"""
        import inspect

        from app.events.types import StreamEvent, StreamEventType

        source = Path(inspect.getsourcefile(StreamEvent)).read_text(encoding="utf-8")
        assert "json.dumps" in source, "to_sse 不再 JSON 编码 —— 注入通道被打开"

        frame = StreamEvent(
            type=StreamEventType.TOKEN, data={"content": "a\n\nb"},
        ).to_sse()
        assert frame.count("\n") == 2, f"帧应只有结尾的 \\n\\n：{frame!r}"
        assert frame.endswith("\n\n")
        assert "\\n\\n" in frame, f"内容换行应被转义为字面 \\n\\n：{frame!r}"


# ═══════════════════════════════════════════════════════════════════
# Part C —— 为什么 `sse_sanitize` 不该接线
# ═══════════════════════════════════════════════════════════════════


class TestSanitizeIsNotWireable:

    @staticmethod
    def _sanitize():
        from app.utils.sse_response import sse_sanitize

        return sse_sanitize

    def test_fg_c01_frame_level_wiring_would_destroy_the_frame(self):
        """帧层接线：帧结束符就是 `\\n\\n`，会被 `sse_sanitize` 吃掉。"""
        sse_sanitize = self._sanitize()
        frame = 'data: {"type": "done"}\n\n'
        sanitized = sse_sanitize(frame)
        assert sanitized == 'data: {"type": "done"}  ', (
            "若此断言变化，说明帧层接线已不再破坏帧 —— 需要重新评审接线方案"
        )
        assert not sanitized.endswith("\n\n"), "帧结束符被破坏，客户端将无法切帧"

    def test_fg_c02_content_level_wiring_would_damage_markdown(self):
        """内容层接线：markdown 空行（`\\n\\n`）会变成两个空格。"""
        sse_sanitize = self._sanitize()
        assert sse_sanitize("第一段\n\n第二段") == "第一段  第二段", (
            "若此断言变化，说明内容层接线的副作用已改变 —— 需要重新评审接线方案"
        )
        # 而这是**真实存在**的内容形态（LLM 输出的 markdown 段落分隔）
        assert sse_sanitize("## 标题\n\n正文") != "## 标题\n\n正文"
