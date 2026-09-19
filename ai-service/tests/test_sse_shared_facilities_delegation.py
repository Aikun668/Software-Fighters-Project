"""公共设施抽取后的委派与结构契约（Task 5）。

与 `test_sse_shared_facilities_contract.py` 的分工：
- 那边锁**行为**（抽取前后响应字节不变）；
- 这边锁**结构**——证明 8 个端点真的走了共享工厂、重复样板真的没了，
  以及两处「边界没被破坏」（`sse_heartbeat.py` 仍不依赖 FastAPI、
  `sse_sanitize` 本轮确实没有接线）。

替身与请求样例直接复用契约文件的（`tests/` 是包，可正常 import），
避免两处各养一份会漂移的 stub。
"""

import ast
import inspect
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

import internal_api
from tests.test_sse_shared_facilities_contract import (
    SSE_CASES,
    SSE_CASE_NAMES,
    SSE_ROUTE_FUNCTIONS,
    _make_app,
    _parse_events,
)

AI_SERVICE_DIR = Path(internal_api.__file__).resolve().parent


def _app() -> FastAPI:
    return _make_app()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test")


def _spy_sse_response(monkeypatch) -> list[dict]:
    """记录 `internal_api.sse_response` 的调用，用于证明端点确实走了共享工厂。"""
    calls: list[dict] = []
    real = internal_api.sse_response

    def wrapper(event_generator, **kwargs):
        calls.append(kwargs)
        return real(event_generator, **kwargs)

    monkeypatch.setattr(internal_api, "sse_response", wrapper)
    return calls


def _spy_safe_export_path(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    real = internal_api.safe_export_path

    def wrapper(filename, **kwargs):
        calls.append({"filename": filename, **kwargs})
        return real(filename, **kwargs)

    monkeypatch.setattr(internal_api, "safe_export_path", wrapper)
    return calls


# ═══════════════════════════════════════════════════════════════════
# D01..D08 —— 8 个 SSE 端点：真实路由 → 真实工厂 → 真实心跳
# ═══════════════════════════════════════════════════════════════════

class TestDelegationToSseResponse:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case_name", SSE_CASE_NAMES)
    async def test_d01_d08_each_sse_endpoint_goes_through_factory(
        self, monkeypatch, case_name,
    ):
        path, payload, install = SSE_CASES[case_name]
        install(monkeypatch)
        calls = _spy_sse_response(monkeypatch)

        async with _client() as client:
            async with client.stream("POST", path, json=payload) as resp:
                body = "".join([chunk async for chunk in resp.aiter_text()])
                status = resp.status_code
                media_type = resp.headers.get("content-type", "")

        assert status == 200, case_name
        assert media_type.startswith("text/event-stream"), (case_name, media_type)
        assert len(calls) == 1, f"{case_name} 应恰好调用一次 sse_response，实际 {len(calls)}"

        events = _parse_events(body)
        assert events, f"{case_name} 未产生任何事件"
        assert events[-1].get("type") == "done", (case_name, events)
        assert [e.get("type") for e in events].count("done") == 1, (case_name, events)

    @pytest.mark.asyncio
    async def test_d08b_response_object_is_the_factory_product(self, monkeypatch):
        """端点返回的就是工厂产物本身，而不是另起炉灶拼的响应。"""
        path, payload, install = SSE_CASES["resources_generate"]
        install(monkeypatch)

        captured = {}
        real = internal_api.sse_response

        def wrapper(event_generator, **kwargs):
            captured["response"] = real(event_generator, **kwargs)
            return captured["response"]

        monkeypatch.setattr(internal_api, "sse_response", wrapper)

        async with _client() as client:
            await client.post(path, json=payload)

        assert isinstance(captured["response"], StreamingResponse)
        assert captured["response"].media_type == "text/event-stream"


# ═══════════════════════════════════════════════════════════════════
# D09..D11 —— 3 个下载端点：三档错误信封逐字比对 + 委派证明
# ═══════════════════════════════════════════════════════════════════

DOWNLOAD_CASES = [
    ("/internal/resources/download-pptx", ".pptx"),
    ("/internal/resources/download-docx", ".docx"),
    ("/internal/resources/download-pdf", ".pdf"),
]

UNSUPPORTED = {
    "success": False, "errorCode": "INVALID_REQUEST", "error": "不支持的文件类型",
}
ILLEGAL_PATH = {
    "success": False, "errorCode": "INVALID_REQUEST", "error": "非法文件路径",
}
MISSING = {
    "success": False, "errorCode": "NOT_FOUND", "error": "文件不存在或已过期",
}


class TestDownloadGuardDelegation:

    @pytest.fixture(autouse=True)
    def _tmp_exports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(internal_api, "_EXPORTS_DIR", str(tmp_path))
        self.exports_dir = tmp_path

    async def _symlink_escape_probe(self, client, route: str, ext: str):
        """造一个指向导出目录之外的符号链接；平台不允许时返回 None。"""
        outside = self.exports_dir.parent / f"outside{ext.replace('.', '_')}"
        outside.mkdir(exist_ok=True)
        (outside / "secret").write_bytes(b"s")

        link = self.exports_dir / f"escape{ext}"
        if link.is_symlink() or link.exists():
            link.unlink()
        try:
            os.symlink(outside / "secret", link)
        except (OSError, NotImplementedError):
            return None

        resp = await client.get(route, params={"filename": f"escape{ext}"})
        return resp.status_code, resp.json()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,ext", DOWNLOAD_CASES)
    async def test_d09_d11_three_error_tiers_verbatim(self, route, ext):
        other_ext = ".pdf" if ext != ".pdf" else ".pptx"

        async with _client() as client:
            # ① 扩展名不符：扩展名校验先于一切路径判断
            unsupported = await client.get(
                route, params={"filename": f"ghost{other_ext}"},
            )
            # ② 文件不存在
            missing = await client.get(route, params={"filename": f"ghost{ext}"})
            # ③ 路径逃逸（符号链接，纵深防御分支）
            illegal = await self._symlink_escape_probe(client, route, ext)

        assert (unsupported.status_code, unsupported.json()) == (400, UNSUPPORTED)
        assert (missing.status_code, missing.json()) == (404, MISSING)
        if illegal is not None:
            assert illegal == (400, ILLEGAL_PATH)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route,ext", DOWNLOAD_CASES)
    async def test_d11b_download_goes_through_shared_guard(self, route, ext, monkeypatch):
        (self.exports_dir / f"export_1{ext}").write_bytes(b"payload")
        calls = _spy_safe_export_path(monkeypatch)

        async with _client() as client:
            resp = await client.get(route, params={"filename": f"export_1{ext}"})

        assert resp.status_code == 200, resp.text
        assert resp.content == b"payload"
        assert len(calls) == 1, f"{route} 应恰好调用一次 safe_export_path，实际 {len(calls)}"
        assert calls[0]["allowed_ext"] == ext
        assert calls[0]["filename"] == f"export_1{ext}"


# ═══════════════════════════════════════════════════════════════════
# D12..D17 —— 结构断言：重复样板真的没了，边界没被破坏
# ═══════════════════════════════════════════════════════════════════

class TestStructuralClosure:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route_name", SSE_ROUTE_FUNCTIONS)
    async def test_d12_endpoint_bodies_have_no_sse_boilerplate(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))

        assert "StreamingResponse(" not in source, f"{route_name} 仍在自建响应"
        assert "sse_heartbeat_generator(" not in source, f"{route_name} 仍直接引用心跳包装器"

    @pytest.mark.asyncio
    async def test_d13_internal_api_dropped_ssrf_symbols(self):
        assert not hasattr(internal_api, "_is_internal_url")
        assert not hasattr(internal_api, "_SSRF_BLOCKED_NETWORKS")
        assert not hasattr(internal_api, "_SSRF_DECIMAL_IP")
        assert not hasattr(internal_api, "_SSRF_HEX_IP")
        assert not hasattr(internal_api, "_SSRF_OCTAL_IP")

        source = Path(internal_api.__file__).read_text(encoding="utf-8")
        assert "_SSRF_" not in source, "SSRF 正则残留在 internal_api"

    @pytest.mark.asyncio
    async def test_d13b_internal_api_dropped_dead_sse_sanitize(self):
        assert not hasattr(internal_api, "_sse_sanitize"), "旧名仍在，归位未完成"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("route_name", [
        "download_pptx", "download_docx", "download_pdf",
    ])
    async def test_d14_download_bodies_have_no_path_guard(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))

        assert "os.path.realpath(" not in source, f"{route_name} 仍在自建路径守卫"
        assert "os.path.basename(filename)" not in source, f"{route_name} 仍在自建 basename"
        assert "safe_export_path(" in source, f"{route_name} 未走共享守卫"

    @pytest.mark.asyncio
    async def test_d15_sse_response_module_has_no_business_deps(self):
        module = __import__("app.utils.sse_response", fromlist=["sse_response"])
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        allowed = {"typing", "fastapi.responses", "app.utils.sse_heartbeat"}
        assert imported <= allowed, f"工厂模块混入了额外依赖：{sorted(imported - allowed)}"

    @pytest.mark.asyncio
    async def test_d16_heartbeat_module_still_framework_free(self):
        from app.utils import sse_heartbeat

        tree = ast.parse(Path(sse_heartbeat.__file__).read_text(encoding="utf-8"))

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        assert "fastapi" not in imported
        assert not any(name.startswith("fastapi") for name in imported)
        assert not any(name.startswith("starlette") for name in imported)

    @pytest.mark.asyncio
    async def test_d17_sse_sanitize_is_still_unwired(self):
        """「未接线锁」：本轮只把 sse_sanitize 归位，没有接线。

        生产代码（`internal_api.py` + `app/`）里不得出现任何 `sse_sanitize(...)` **调用**。
        将来真的接线时必须显式改掉这条测试——这就是它存在的意义。
        """
        targets = [Path(internal_api.__file__)]
        targets.extend(p for p in (AI_SERVICE_DIR / "app").rglob("*.py"))

        callers = []
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "sse_sanitize":
                        callers.append(f"{path.name}:{node.lineno}")

        assert callers == [], (
            f"sse_sanitize 被接线了：{callers}。"
            "本轮明确「只归位不接线」，若确实要接线，请先补恶意换行/伪造 SSE 帧契约测试，"
            "并显式更新本断言。"
        )
