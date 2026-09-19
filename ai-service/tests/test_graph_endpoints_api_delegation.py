"""图谱域收口同进程 ASGI 委派测试（Task 5）。

用 httpx ASGITransport 起同进程 HTTP，验证收窄后的真实链路：

- KG-D01..D03: 读/写/抽取端点 → _get_graph_center() → GraphCenter.<入口>
  → GraphService 纯算法 → api_success 序列化（真实 Center + 真实 Service）
- KG-D04..D06: 委派签名 —— API 把 body 字段原样传给 Center，且
  写路径在 API 边界完成 pydantic → 纯 dict 的适配
- KG-D07..D10: 错误映射原样保留（404 / 400 / 500）
- KG-D11..D14: inspect.getsource 结构断言 —— 14 个路由内不再持有图谱域
  业务符号；模块级符号已删除；Center 不依赖 fastapi

不调真实 LLM：GraphService.suggest_edges 与 extract_knowledge_nodes 被换成
固定输出，其余（GraphService / GraphCenter / 序列化 / 错误映射）全走真实代码。
"""

import ast
import contextlib
import inspect
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import app.services.graph_service as graph_service_module
import app.services.knowledge_extraction as knowledge_extraction_module
import internal_api
from app.centers.graph_center import GraphCenter
from app.services.graph_service import GraphService
from internal_api import router

SKELETON_NODE_COUNT = 10

GRAPH_ROUTES = [
    "get_knowledge_graph",
    "get_node_card",
    "graph_extract",
    "graph_nodes",
    "update_masteries",
    "reload_graph",
    "recommend_next_node",
    "get_progress_summary",
    "check_prerequisites",
    "delete_node",
    "update_node",
    "suggest_edges",
    "export_mermaid",
    "get_layered_graph",
]

# 只禁「Service 层与旧接收者」的符号，不禁 Center 的方法名——两者大量同名
# （export_mermaid / check_prerequisites …），禁方法名会误伤正当的
# `_get_graph_center().export_mermaid(...)`。真正的红线是：路由体内不得出现
# Service 类、抽取函数、计划域工厂、以及收口前的局部接收者 `graph_service.`。
FORBIDDEN_SYMBOLS = [
    "GraphService",
    "PlanService",
    "extract_knowledge_nodes",
    "get_plan_service",
    "graph_service.",
    "_get_graph_service()",
]

EXTRACT_GROUPS = {
    "primary": [{"node_id": "overfitting", "confidence": 0.91}],
    "related": [{"node_id": "gradient_variants", "confidence": 0.72}],
    "broad": [{"node_id": "ml_basics", "confidence": 0.55}],
    "all": [
        {"node_id": "overfitting", "confidence": 0.91},
        {"node_id": "gradient_variants", "confidence": 0.72},
        {"node_id": "ml_basics", "confidence": 0.55},
    ],
}

SUGGESTIONS = [
    {"source": "overfitting", "target": "cnn", "relation": "depends_on",
     "rationale": "正则化影响卷积网络训练"},
]


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        msg = errors[0]["msg"] if errors else "请求参数验证失败"
        loc = errors[0].get("loc", [])
        if loc:
            field = str(loc[-1]) if len(loc) > 1 else str(loc[0])
            msg = f"字段 '{field}' {msg}"
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg, "error_code": "INVALID_REQUEST"},
        )

    app.include_router(router)
    return app


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test",
    ) as client:
        yield client


# ═══════════════════════════════════════════════════════════════════
# 基础设施
# ═══════════════════════════════════════════════════════════════════

@contextlib.contextmanager
def _fresh_state():
    """三条单例路径 + 两个替身一起复位，退出时全部还原。

    GraphService 是有状态内存单例，不复位会让内存变异跨用例泄漏；
    `_graph_center_singleton` 在构造时就抓住当时的 GraphService 实例，
    所以也必须一起复位。
    """
    fresh = GraphService()
    outer_before = internal_api._graph_service_singleton
    inner_before = graph_service_module._graph_service
    center_before = internal_api._graph_center_singleton
    extraction_before = knowledge_extraction_module.extract_knowledge_nodes
    suggest_before = vars(GraphService)["suggest_edges"]

    async def _fake_extraction(*, course_id, user_message, assistant_reply,
                               existing_node_ids=None):
        return groups_snapshot()

    async def _fake_suggest(self, course_id=None):
        return [dict(item) for item in SUGGESTIONS]

    def groups_snapshot():
        return {k: [dict(item) for item in v] for k, v in EXTRACT_GROUPS.items()}

    internal_api._graph_service_singleton = fresh
    graph_service_module._graph_service = fresh
    internal_api._graph_center_singleton = None
    knowledge_extraction_module.extract_knowledge_nodes = _fake_extraction
    GraphService.suggest_edges = _fake_suggest
    try:
        yield fresh
    finally:
        internal_api._graph_service_singleton = outer_before
        graph_service_module._graph_service = inner_before
        internal_api._graph_center_singleton = center_before
        knowledge_extraction_module.extract_knowledge_nodes = extraction_before
        GraphService.suggest_edges = suggest_before


@contextlib.contextmanager
def _recording_center():
    """把 `_get_graph_center()` 换成「记录每次调用后转交真实 GraphCenter」的替身。

    用于锁委派签名（方法名 + 关键字参数），链路本身仍走真实 Center。
    """
    calls: list[tuple[str, dict]] = []
    real = GraphCenter(graph_service=GraphService())
    previous = internal_api._graph_center_singleton
    holder = _Holder(real, calls)
    internal_api._graph_center_singleton = holder
    try:
        yield calls
    finally:
        internal_api._graph_center_singleton = previous


class _Holder:
    def __init__(self, real, calls):
        self._real = real
        self._calls = calls

    def __getattr__(self, name):
        target = getattr(self._real, name)

        async def _call(**kwargs):
            self._calls.append((name, kwargs))
            return await target(**kwargs)

        return _call


@contextlib.contextmanager
def _boom_method(cls, name: str):
    original = vars(cls)[name]

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    setattr(cls, name, _raise)
    try:
        yield
    finally:
        setattr(cls, name, original)


# ═══════════════════════════════════════════════════════════════════
# KG-D01..D03 真实链路
# ═══════════════════════════════════════════════════════════════════

class TestRealChain:

    @pytest.mark.asyncio
    async def test_d01_get_graph_through_real_center(self, async_client):
        """KG-D01: /knowledge-graph 走真实 GraphCenter + 真实 GraphService。"""
        with _fresh_state():
            r = await async_client.post(
                "/internal/knowledge-graph/ai_intro",
                json={"masteries": {"ai_overview": 0.9}},
            )

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == ["course_id", "version", "nodes", "edges"]
        assert len(data["nodes"]) == SKELETON_NODE_COUNT
        assert data["nodes"][0]["mastery"] == 0.9

    @pytest.mark.asyncio
    async def test_d02_write_then_read_reflects_mutation(self, async_client):
        """KG-D02: 写路径经 Center 落到 Service，再读能看见（真实内存语义）。"""
        with _fresh_state():
            added = await async_client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_node",
                             "data": {"id": "dyn_d02", "name": "D02"}}],
            })
            read = await async_client.post(
                "/internal/knowledge-graph/ai_intro", json={"masteries": {}},
            )

        assert added.status_code == 200
        assert [n["id"] for n in added.json()["data"]["nodes"]][-1] == "dyn_d02"
        assert len(read.json()["data"]["nodes"]) == SKELETON_NODE_COUNT + 1

    @pytest.mark.asyncio
    async def test_d03_extract_through_real_center(self, async_client):
        """KG-D03: /graph/extract 经真实 GraphCenter 组装四键信封。"""
        with _fresh_state():
            r = await async_client.post("/internal/graph/extract", json={
                "course_id": "ai_intro", "user_message": "什么是过拟合",
                "assistant_reply": "过拟合指模型在训练集上表现过好",
                "existing_node_ids": ["backprop"],
            })

        assert r.status_code == 200
        assert list(r.json()["data"].keys()) == [
            "primary", "related", "broad", "candidates",
        ]
        assert r.json()["data"]["candidates"] == EXTRACT_GROUPS["all"]


# ═══════════════════════════════════════════════════════════════════
# KG-D04..D06 委派签名
# ═══════════════════════════════════════════════════════════════════

class TestDelegationSignature:

    @pytest.mark.asyncio
    async def test_d04_read_route_passes_body_fields(self, async_client):
        """KG-D04: 所有字段以关键字参数原样交出，无位置参数、无加工。"""
        with _fresh_state(), _recording_center() as calls:
            await async_client.post(
                "/internal/knowledge-graph/ai_intro/node/ml_basics",
                json={"masteries": {"ai_overview": 0.9}, "total_exercises": 7,
                      "last_practiced": "2026-09-01T00:00:00Z"},
            )

        assert calls == [("get_node_card", {
            "course_id": "ai_intro",
            "node_id": "ml_basics",
            "masteries": {"ai_overview": 0.9},
            "total_exercises": 7,
            "last_practiced": "2026-09-01T00:00:00Z",
        })]

    @pytest.mark.asyncio
    async def test_d05_write_route_adapts_pydantic_to_plain_dict(self, async_client):
        """KG-D05: 写路径在 API 边界把 pydantic 模型适配成纯 dict。"""
        with _fresh_state(), _recording_center() as calls:
            await async_client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [
                    {"action": "add_node", "data": {"id": "dyn_d05", "name": "D05"}},
                    {"action": "add_edge",
                     "data": {"source": "ai_overview", "target": "dyn_d05"}},
                ],
            })

        assert len(calls) == 1
        name, kwargs = calls[0]
        assert name == "apply_updates"
        assert kwargs["course_id"] == "ai_intro"
        assert kwargs["updates"] == [
            {"action": "add_node", "data": {"id": "dyn_d05", "name": "D05"}},
            {"action": "add_edge",
             "data": {"source": "ai_overview", "target": "dyn_d05"}},
        ]
        assert all(isinstance(u, dict) for u in kwargs["updates"])

    @pytest.mark.asyncio
    async def test_d06_masteries_route_adapts_events_to_dicts(self, async_client):
        """KG-D06: 掌握度事件同样在边界转成纯 dict，score 缺省为 None。"""
        with _fresh_state(), _recording_center() as calls:
            await async_client.post("/internal/graph/masteries", json={
                "course_id": "ai_intro", "masteries": {"ml_basics": 0.5},
                "events": [
                    {"node_id": "ml_basics", "event_type": "exercise_done",
                     "score": 0.8},
                    {"node_id": "dl_basics", "event_type": "resource_viewed"},
                ],
            })

        assert calls == [("update_masteries", {
            "course_id": "ai_intro",
            "masteries": {"ml_basics": 0.5},
            "events": [
                {"node_id": "ml_basics", "event_type": "exercise_done", "score": 0.8},
                {"node_id": "dl_basics", "event_type": "resource_viewed", "score": None},
            ],
        })]


# ═══════════════════════════════════════════════════════════════════
# KG-D07..D10 错误映射
# ═══════════════════════════════════════════════════════════════════

class TestErrorMapping:

    @pytest.mark.asyncio
    async def test_d07_node_card_missing_maps_to_404(self, async_client):
        """KG-D07: Center 抛 ValueError → 路由映射 404。"""
        with _fresh_state():
            r = await async_client.post(
                "/internal/knowledge-graph/ai_intro/node/nope",
                json={"masteries": {}},
            )

        assert r.status_code == 404
        assert r.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "节点不存在",
        }

    @pytest.mark.asyncio
    async def test_d08_delete_skeleton_maps_to_400_with_message(self, async_client):
        """KG-D08: Center 抛 ValueError → 400，文案为 str(e) 原文。"""
        with _fresh_state():
            r = await async_client.post(
                "/internal/graph/nodes/ai_overview/delete",
                json={"course_id": "ai_intro"},
            )

        assert r.status_code == 400
        body = r.json()
        assert body["errorCode"] == "INVALID_REQUEST"
        assert "骨架节点不可删除" in body["error"]

    @pytest.mark.asyncio
    async def test_d09_service_failure_maps_to_500(self, async_client):
        """KG-D09: Service 抛非 ValueError → 500 INTERNAL_ERROR。"""
        with _fresh_state(), _boom_method(GraphService, "get_progress_summary"):
            r = await async_client.post(
                "/internal/graph/progress",
                json={"course_id": "ai_intro", "masteries": {}},
            )

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "进度概要获取失败",
        }

    @pytest.mark.asyncio
    async def test_d10_masteries_has_no_try_except(self, async_client):
        """KG-D10: /graph/masteries 是全域唯一**不**包错误信封的端点。

        路由体内没有 try/except，Center 里冒出的非 ValueError 直接上抛，
        由框架兜成 500（非 api_error 信封）——收口前后都必须保持。
        """
        with _fresh_state(), _boom_method(GraphService, "recommend_next_node"):
            ok = await async_client.post(
                "/internal/graph/next-node",
                json={"course_id": "ai_intro", "masteries": {}},
            )
        assert ok.status_code == 500
        assert ok.json()["error"] == "节点推荐失败"

        source = inspect.getsource(internal_api.update_masteries)
        assert "except" not in source

        # 无 try/except ⇒ 异常穿出路由，不会被折成 api_error 信封
        with _fresh_state(), _boom_method(GraphCenter, "update_masteries"):
            with pytest.raises(RuntimeError, match="boom"):
                await async_client.post("/internal/graph/masteries", json={
                    "course_id": "ai_intro", "masteries": {},
                    "events": [{"node_id": "ml_basics",
                                "event_type": "resource_viewed"}],
                })


# ═══════════════════════════════════════════════════════════════════
# KG-D11..D14 结构断言
# ═══════════════════════════════════════════════════════════════════

class TestStructure:

    @pytest.mark.parametrize("route_name", GRAPH_ROUTES)
    def test_d11_route_delegates_to_graph_center(self, route_name):
        """恰好一次业务调用：一个路由只找一个 Center，不做分叉编排。"""
        source = inspect.getsource(getattr(internal_api, route_name))
        assert source.count("_get_graph_center()") == 1, (
            f"{route_name} 的 _get_graph_center() 调用次数 != 1"
        )

    @pytest.mark.parametrize("route_name", GRAPH_ROUTES)
    def test_d12_route_has_no_business_symbols(self, route_name):
        source = inspect.getsource(getattr(internal_api, route_name))
        for symbol in FORBIDDEN_SYMBOLS:
            assert symbol not in source, f"{route_name} 仍含 {symbol}"

    def test_d13_module_level_symbols_removed(self):
        """收口后 API 模块不再持有这两个业务符号（已搜全仓无第三方引用）。"""
        assert not hasattr(internal_api, "extract_knowledge_nodes")
        assert not hasattr(internal_api, "get_plan_service")
        # 装配点仍在：GraphCenter 单例 + 外层 GraphService 包装（遗留保留）
        assert hasattr(internal_api, "_get_graph_center")
        assert hasattr(internal_api, "_get_graph_service")

    @pytest.mark.parametrize("route_name", GRAPH_ROUTES)
    def test_d14_route_body_is_thin(self, route_name):
        """可执行体净行数 ≤ 20（去掉装饰器/docstring/空行/注释后计数）。"""
        source = inspect.getsource(getattr(internal_api, route_name))
        lines = []
        in_doc = False
        for line in source.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if in_doc:
                if '"""' in stripped or "'''" in stripped:
                    in_doc = False
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if stripped.count('"""') < 2 and stripped.count("'''") < 2:
                    in_doc = True
                continue
            if stripped.startswith("@"):
                continue
            lines.append(stripped)
        assert len(lines) <= 20, f"{route_name} 可执行体 {len(lines)} 行 > 20"


def test_d15_graph_center_has_no_fastapi_dependency():
    """GraphCenter 不 import fastapi / pydantic：业务层不做协议适配。

    走 AST 而非源码子串匹配——模块 docstring 里就写着「不 import fastapi」，
    子串匹配会自己命中自己的说明文字。
    """
    module = sys.modules["app.centers.graph_center"]
    tree = ast.parse(inspect.getsource(module))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # 惰性 import 在函数体内，ast.walk 同样能覆盖
    assert "fastapi" not in imported, f"GraphCenter 依赖 fastapi: {imported}"
    assert "pydantic" not in imported, f"GraphCenter 依赖 pydantic: {imported}"
    assert "starlette" not in imported, f"GraphCenter 依赖 starlette: {imported}"
