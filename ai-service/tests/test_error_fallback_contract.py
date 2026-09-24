"""错误兜底契约（GUIDE P2 第 2 步「统一错误」/ Task 3）。

摸底结论：**错误信封其实早已统一**。`internal_api.py` 内 32 处
`except Exception as e:` 中，28 处 JSON 兜底的形状完全一致
（`logger.error(...)` + `return api_error(ErrorCode.X, "中文", status_code=500)`）。
真正没统一的只有三处漏网 + 一处真空白：

1. 2 个 SSE 端点的兜底**手写 `json.dumps` 帧**，绕过了 `app/events/types.py` 的事件工厂；
2. `eval_judge` 把**异常原文**回进响应体（信息泄露）；
3. 32 处里 26 处缺 `exc_info=True`，catch-all 兜到意外异常却没有栈；
4. `main.py` **没有全局 500 兜底** —— 14 个无 `try` 的端点里 8 个是普通 JSON 端点，
   一旦抛异常响应体是 FastAPI 默认的 `Internal Server Error`（text/plain！），
   前端按 `success`/`errorCode` 解析只能拿到空值。

之所以先写这个文件：`AI_SERVICE_ARCHITECTURE_GUIDE.md` line 148
「不要在没有契约测试前搬动 SSE、错误响应和安全校验」。这里动的正是错误响应。

- **Part A（`ERR-A*`）**：现有行为锁定，改造前后都必须全绿。含三条「不得改变语义」
  的回归锁（`HTTPException` / 参数校验 / SSE 成功路径），对应用户对本轮追加的约束。
- **Part B（`ERR-B*`）**：本轮要改的项。Task 3 时红，Task 4/5/6 后转绿。

⚠️ 用**真实 `main.app`**（而非测试自建 app）打请求：本轮要验证的正是 `main.py`
的异常处理装配，自建 app 会把被验证的对象替换掉。
`raise_app_exceptions=False` 是必需的 —— 否则未捕获异常会被测试框架直接抛出，
观测不到兜底响应（Starlette 的 `ServerErrorMiddleware` 只在「不抛出」时才产响应）。
"""

import ast
import inspect
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import internal_api
import main
from tests.test_internal_api_package_contract import ai_service_dir, internal_api_sources


AI_SERVICE_DIR = ai_service_dir()


# 失败路径的**逐字节**期望值，原样抄自改造前的实测响应。
PROFILE_CHAT_FAILURE_BYTES = (
    'data: {"type": "error", "content": "画像对话失败，请稍后重试"}\n\n'
    'data: {"type": "done"}\n\n'
)
INQUIRY_PLAN_FAILURE_BYTES = (
    'data: {"type": "progress", "stage": "path", "content": "正在为「反向传播」规划学习路径..."}\n\n'
    'data: {"type": "error", "content": "学习路径生成失败，请稍后重试"}\n\n'
    'data: {"type": "done"}\n\n'
)

PROFILE_CHAT_PAYLOAD = {"messages": [{"role": "user", "content": "我是谁"}], "user_id": 1}
INQUIRY_PLAN_PAYLOAD = {
    "original_message": "讲讲反向传播", "answers": ["要数学推导"], "user_id": 1,
}

# 8 个 SSE 端点的路由函数名（与共享设施契约的 SSE_ROUTE_FUNCTIONS 同源）
SSE_ROUTE_FUNCTIONS = [
    "profile_chat", "resources_generate", "tutor_chat", "exercise_generate",
    "solve_question", "_unified_chat", "inquiry_resolve", "inquiry_resolve_plan",
]


class _RaisingWorkflow:
    """`run()` 直接抛异常的 workflow 替身。"""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def run(self, state):
        raise self._exc


class _RaisingStatusWorkflow:
    """`check_profile_status()` 直接抛异常的 workflow 替身。"""

    def __init__(self, exc: Exception):
        self._exc = exc

    def check_profile_status(self, student_profile):
        raise self._exc


class _OkInquiry:
    def resolve(self, original_message, answers, **kwargs):
        return {"topic": "反向传播", "context_note": "note", "suggested_types": ["document"]}


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=main.app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


async def _raw(client, path: str, payload: dict) -> tuple[int, str]:
    async with client.stream("POST", path, json=payload) as resp:
        chunks = [chunk async for chunk in resp.aiter_text()]
        return resp.status_code, "".join(chunks)


def _except_handlers_without_exc_info() -> list[str]:
    """返回所有 `except Exception` 缺 `exc_info` 的处理器位置（`文件:行`）。

    扫描范围是 `internal_api` 的**全部生产源码**（拆包前=单文件，拆包后=包内全文件），
    由 `internal_api_sources()` 提供，断言语义不变。
    """
    offenders: list[str] = []
    for path in internal_api_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None or ast.unparse(node.type) != "Exception":
                continue
            logged_with_traceback = False
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                    continue
                if call.func.attr not in ("error", "exception", "warning"):
                    continue
                if any(kw.arg == "exc_info" for kw in call.keywords):
                    logged_with_traceback = True
            if not logged_with_traceback:
                offenders.append(f"{path.name}:{node.lineno}")
    return offenders


# ═══════════════════════════════════════════════════════════════════
# Part A —— 现有行为锁定（改造前后都必须全绿）
# ═══════════════════════════════════════════════════════════════════


class TestPartAExistingFallbacks:

    @pytest.mark.asyncio
    async def test_err_a01_profile_chat_failure_emits_error_then_single_done(
        self, async_client, monkeypatch,
    ):
        monkeypatch.setattr(
            internal_api, "_get_profile_workflow",
            lambda: _RaisingWorkflow(RuntimeError("画像爆炸")),
        )
        status, raw = await _raw(async_client, "/internal/profile/chat", PROFILE_CHAT_PAYLOAD)

        assert status == 200
        assert raw == PROFILE_CHAT_FAILURE_BYTES

    @pytest.mark.asyncio
    async def test_err_a02_inquiry_plan_failure_emits_error_then_single_done(
        self, async_client, monkeypatch,
    ):
        monkeypatch.setattr(internal_api, "_get_inquiry_service", lambda: _OkInquiry())
        monkeypatch.setattr(
            internal_api, "_get_path_workflow",
            lambda: _RaisingWorkflow(RuntimeError("路径爆炸")),
        )
        status, raw = await _raw(
            async_client, "/internal/inquiry/resolve/plan", INQUIRY_PLAN_PAYLOAD,
        )

        assert status == 200
        assert raw == INQUIRY_PLAN_FAILURE_BYTES

    @pytest.mark.asyncio
    async def test_err_a03_eval_judge_disabled_by_default(self, async_client, monkeypatch):
        monkeypatch.delenv("EVAL_JUDGE_ENABLED", raising=False)
        resp = await async_client.post("/internal/eval/judge", json={"message": "评测"})

        assert resp.status_code == 403
        assert resp.json() == {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "评测端点未启用",
        }

    @pytest.mark.asyncio
    async def test_err_a04_unknown_route_still_returns_http_exception_shape(self, async_client):
        """回归锁：全局兜底不得吞掉 `HTTPException` 的既有语义。"""
        resp = await async_client.get("/internal/definitely-not-a-route")

        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not Found"}

    @pytest.mark.asyncio
    async def test_err_a05_validation_error_keeps_its_own_envelope(self, async_client):
        """回归锁：`RequestValidationError` 的 400 信封不得被全局兜底改变。"""
        resp = await async_client.post("/internal/api/chat", json={})

        assert resp.status_code == 400
        assert resp.json() == {
            "success": False,
            "error": "字段 'message' Field required",
            "error_code": "INVALID_REQUEST",
        }

    @pytest.mark.asyncio
    async def test_err_a06_sse_success_path_is_not_intercepted(self, async_client, monkeypatch):
        """回归锁：SSE 成功路径仍是 200 + text/event-stream，未被全局兜底包成 JSON。

        全局 `Exception` handler 只该在「响应发出前就炸」时接手；流式响应一旦
        开始发送就不在它的作用范围内。本用例用真实媒体类型与事件序列把这条边界钉死。
        """

        class _OkWorkflow:
            async def run(self, state):
                return {"response": "画像正文", "profile_changed": False, "profile_complete": False}

        monkeypatch.setattr(internal_api, "_get_profile_workflow", lambda: _OkWorkflow())
        async with async_client.stream(
            "POST", "/internal/profile/chat", json=PROFILE_CHAT_PAYLOAD,
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            raw = "".join([chunk async for chunk in resp.aiter_text()])

        assert raw.count('"type": "done"') == 1
        assert raw.rstrip().endswith('data: {"type": "done"}')


# ═══════════════════════════════════════════════════════════════════
# Part B —— 本轮要改的项（Task 3 红，Task 4/5/6 后转绿）
# ═══════════════════════════════════════════════════════════════════


class TestPartBUnification:

    def test_err_b01_sse_fallbacks_go_through_event_factories(self):
        """两处 SSE 兜底必须改由 `error_content_event` / `done_event` 产出。

        ⚠️ 不能用 `error_event(stage, message)` —— 它同时写 `message` 和 `content`
        两个键，字节会变。这是本轮最容易踩的坑。
        """
        for name in ("profile_chat", "inquiry_resolve_plan"):
            body = inspect.getsource(getattr(internal_api, name))
            assert "error_content_event(" in body, f"{name} 的错误帧未走事件工厂"
            assert "done_event()" in body, f"{name} 的 done 帧未走事件工厂"
            assert "json.dumps({'type': 'error'" not in body, f"{name} 仍手写错误帧"

    @pytest.mark.asyncio
    async def test_err_b02_eval_judge_does_not_echo_exception_text(
        self, async_client, monkeypatch,
    ):
        """异常原文不得回进响应体；只允许进日志。"""
        monkeypatch.setenv("EVAL_JUDGE_ENABLED", "1")
        secret = "sk-live-DEADBEEF"
        internal = "/opt/secret/path/config.yaml"

        def _boom():
            raise RuntimeError(f"{secret} 读取 {internal} 失败")

        from app.services import llm_service
        monkeypatch.setattr(llm_service, "get_llm_service", _boom)

        resp = await async_client.post("/internal/eval/judge", json={"message": "评测一下"})

        assert resp.status_code == 500
        assert resp.json()["errorCode"] == "INTERNAL_ERROR"
        assert secret not in resp.text, "响应体泄露了凭据"
        assert internal not in resp.text, "响应体泄露了内部路径"

    def test_err_b03_every_broad_except_logs_a_stack_trace(self):
        """`except Exception` 是 catch-all，兜到的一定是意外，必须留栈。"""
        offenders = _except_handlers_without_exc_info()
        assert offenders == [], f"以下 except 处理器缺 exc_info：{offenders}"

    def test_err_b04_main_registers_a_global_exception_handler(self):
        source = (AI_SERVICE_DIR / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        handlers: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if "exception_handler" in text:
                    handlers.append(text)
        assert any("Exception" in h and "HTTPException" not in h and "Validation" not in h
                   for h in handlers), f"main.py 未注册全局 Exception 兜底，现有：{handlers}"

    @pytest.mark.asyncio
    async def test_err_b05_unhandled_exception_returns_the_standard_envelope(
        self, async_client, monkeypatch,
    ):
        """无 try 的 JSON 端点抛异常时，也必须给出标准信封而非 text/plain。"""
        monkeypatch.setattr(
            internal_api, "_get_profile_workflow",
            lambda: _RaisingStatusWorkflow(RuntimeError("配置爆炸")),
        )
        resp = await async_client.post(
            "/internal/profile/workflow/status", json={"student_profile": {}},
        )

        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {
            "success": False,
            "errorCode": "INTERNAL_ERROR",
            "error": "服务内部错误，请稍后重试",
        }

    def test_err_b06_sse_sanitize_stays_unwired(self):
        """跨轮守护锁：`sse_sanitize` 的接线是独立一轮的事，本轮不得顺手接上。

        接线会改变响应字节，必须与「零行为变化」的轮次分开。
        """
        callers: list[str] = []
        roots = [*internal_api_sources(), *sorted((AI_SERVICE_DIR / "app").rglob("*.py"))]
        for path in roots:
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id == "sse_sanitize":
                    callers.append(f"{path.name}:{node.lineno}")
                elif isinstance(func, ast.Attribute) and func.attr == "sse_sanitize":
                    callers.append(f"{path.name}:{node.lineno}")
        assert callers == [], f"sse_sanitize 被接线了（本轮不应发生）：{callers}"
