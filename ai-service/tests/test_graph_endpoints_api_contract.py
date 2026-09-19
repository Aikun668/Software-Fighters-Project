"""图谱域端点收口契约测试（Task 1）。

锁定 `internal_api.py` 里 14 个图谱端点（12 个 `/graph/*` + 2 个 `/knowledge-graph/*`）
的对外契约，作为后续收窄到 `GraphCenter` 的兼容基线：

- Part A（KG-A01..A35）：锁收口**前**的 HTTP 字节行为，收窄后必须保持全绿。
  注入点全部选在「收窄前后都存在」的符号上（`GraphService` 类方法、
  `PlanService.update_mastery` 静态方法、`internal_api.api_success`）。
- Part B（KG-B01..B15）：锁新增 `GraphCenter` 的 14 个业务入口，
  Task 2/3 落地前为 **RED**。

预期 RED 形态（Part B）：
    AttributeError: module 'app.centers.graph_center' has no attribute 'GraphCenter'

**单例隔离（本文件最关键的基础设施）**：`GraphService` 是**有状态单例**，
`add_node` / `add_edge` / `delete_node` / `update_node` 只改内存 `_skeleton_cache`、
不写盘。因此每个用例都通过 `_fresh_graph_service()` 换上全新实例，用完还原，
避免用例之间互相污染。

该 helper 必须同时改写**两条单例路径**：
- `internal_api._get_graph_service()`（外层 `_graph_service_singleton`）—— 13 个路由走这条
- `app.services.graph_service.get_graph_service()`（内层 `_graph_service`）—— `/graph/reload` 直连这条

只改一处会漏（`/graph/reload` 绕过外层包装直接调内层工厂）。
"""

import contextlib

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.services.graph_service as graph_service_module
import app.services.knowledge_extraction as knowledge_extraction_module
import internal_api
from app.services.graph_service import GraphService
from app.services.plan_service import PlanService
from internal_api import router

# 骨架固定数据（data/knowledge_graph_skeleton.json）：10 节点 / 15 边
# get_graph 会再补 6 条 parallel 边 → 21 边；load_skeleton 返回原始 15 边
SKELETON_NODE_COUNT = 10
SKELETON_EDGE_COUNT = 15
GRAPH_EDGE_COUNT_WITH_PARALLEL = 21

GET_GRAPH_DATA_KEYS = ["course_id", "version", "nodes", "edges"]
GRAPH_NODE_KEYS = [
    "id", "name", "type", "description", "difficulty", "category",
    "doc", "mastery", "status", "color",
]
# `add_node` 造出来的节点**没有 `doc` 键**（骨架节点有）：现行实现的真实差异，
# 收口前后都必须保持，故单独锁定。
ADDED_NODE_KEYS = [
    "id", "name", "type", "description", "difficulty", "category",
    "mastery", "status", "color",
]
GRAPH_EDGE_KEYS = ["source", "target", "relation", "rationale"]

# `add_edge` 除写入 1 条显式边，还会触发 `auto_add_parallel_edges` 补 1 条
# parallel 边，故 +2（例：加 ai_overview→cnn 后自动补 ml_basics→cnn）。
GRAPH_EDGE_COUNT_AFTER_ONE_ADD = GRAPH_EDGE_COUNT_WITH_PARALLEL + 2


# ═══════════════════════════════════════════════════════════════════
# 基础设施
# ═══════════════════════════════════════════════════════════════════

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


@pytest.fixture
def client():
    return TestClient(_make_app())


@contextlib.contextmanager
def _fresh_graph_service():
    """把三条单例路径都指向同一个全新 GraphService，退出时还原。

    见模块 docstring：`/graph/reload` 走内层工厂，其余 13 个路由走外层包装，
    只 patch 一处会漏。第三条是 GraphCenter 单例——它在构造时就抓住了当时的
    GraphService 实例（`_get_graph_center()` 装配 `_get_graph_service()`），
    不复位就会拿着上一个用例的服务，导致内存变异跨用例泄漏。
    """
    fresh = GraphService()
    outer_before = internal_api._graph_service_singleton
    inner_before = graph_service_module._graph_service
    center_before = getattr(internal_api, "_graph_center_singleton", None)
    internal_api._graph_service_singleton = fresh
    graph_service_module._graph_service = fresh
    internal_api._graph_center_singleton = None
    try:
        yield fresh
    finally:
        internal_api._graph_service_singleton = outer_before
        graph_service_module._graph_service = inner_before
        internal_api._graph_center_singleton = center_before


_MISSING = object()


@contextlib.contextmanager
def _patch_attr(name: str, value):
    """替换 `internal_api` 的模块属性，退出时还原。

    该属性可能在收口后被删除（如 `extract_knowledge_nodes` 的模块级 import
    随调用点迁进 GraphCenter 而删除），故「原本不存在」时退出即删除，而不是
    还原成一个凭空的属性。
    """
    original = getattr(internal_api, name, _MISSING)
    setattr(internal_api, name, value)
    try:
        yield
    finally:
        if original is _MISSING:
            delattr(internal_api, name)
        else:
            setattr(internal_api, name, original)


@contextlib.contextmanager
def _patch_method(cls, name: str, value):
    """替换类属性并在退出时还原。

    必须从 `vars()` 取原始对象：对 `@staticmethod` 用 `getattr` 拿到的是裸函数，
    还原后静态方法会退化成实例方法（会把第一个实参当 self 吞掉）。
    """
    original = vars(cls)[name] if name in vars(cls) else getattr(cls, name)
    setattr(cls, name, value)
    try:
        yield
    finally:
        setattr(cls, name, original)


@contextlib.contextmanager
def _boom_method(cls, name: str, message: str = "boom"):
    """让指定类方法抛错，用于锁 500 分支。"""
    def _raise(*args, **kwargs):
        raise RuntimeError(message)

    with _patch_method(cls, name, _raise):
        yield


@contextlib.contextmanager
def _boom_success():
    """让路由体内的 `api_success(...)` 抛错，用于锁 500 分支。

    这是唯一一个在收窄前后都稳定存在的注入点：路由永远在同一个 try 里调用
    `api_success`，因此 500 文案可以逐字锁定。
    """
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    with _patch_attr("api_success", _raise):
        yield


@contextlib.contextmanager
def _patch_extraction(fake):
    """同时替换两条抽取注入点，让同一条用例在收口前后都成立。

    收口前路由体用 `internal_api.extract_knowledge_nodes`（模块级 import 绑定
    的函数对象）；收口后调用点移进 `GraphCenter.extract_nodes`，走的是
    `knowledge_extraction` 的模块属性（惰性 import，每次调用现取）。只打一处
    的话，同一断言会因收口而翻红。两处都打，Part A 的字节锁才是真正的
    「前后同一份断言」。
    """
    before = knowledge_extraction_module.extract_knowledge_nodes
    knowledge_extraction_module.extract_knowledge_nodes = fake
    try:
        with _patch_attr("extract_knowledge_nodes", fake):
            yield
    finally:
        knowledge_extraction_module.extract_knowledge_nodes = before


@contextlib.contextmanager
def _stub_extraction(groups: dict):
    """替身知识抽取，返回固定分组并记录调用参数。"""
    calls: list[dict] = []

    async def _fake(*, course_id, user_message, assistant_reply, existing_node_ids=None):
        calls.append({
            "course_id": course_id,
            "user_message": user_message,
            "assistant_reply": assistant_reply,
            "existing_node_ids": existing_node_ids,
        })
        return groups

    with _patch_extraction(_fake):
        yield calls


@contextlib.contextmanager
def _stub_suggest_edges(items: list[dict]):
    """替身补边建议：GraphService 类方法，收窄前后同一注入点。"""
    calls: list[dict] = []

    async def _fake(self, course_id=None):
        calls.append({"course_id": course_id})
        return list(items)

    with _patch_method(GraphService, "suggest_edges", _fake):
        yield calls


# ═══════════════════════════════════════════════════════════════════
# Part A — /knowledge-graph 读路径（KG-A01..A05）
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeGraphRead:

    def test_a01_get_graph_success(self, client):
        """KG-A01: 图谱全量返回 + 掌握度注入 + 节点键序。"""
        with _fresh_graph_service():
            r = client.post(
                "/internal/knowledge-graph/ai_intro",
                json={"masteries": {"ai_overview": 0.9}},
            )

        assert r.status_code == 200
        body = r.json()
        assert list(body.keys()) == ["success", "data"]

        data = body["data"]
        assert list(data.keys()) == GET_GRAPH_DATA_KEYS
        assert data["course_id"] == "ai_intro"
        assert data["version"] == 1
        assert len(data["nodes"]) == SKELETON_NODE_COUNT
        assert len(data["edges"]) == GRAPH_EDGE_COUNT_WITH_PARALLEL
        assert list(data["edges"][0].keys()) == GRAPH_EDGE_KEYS

        first = data["nodes"][0]
        assert list(first.keys()) == GRAPH_NODE_KEYS
        assert first == {
            "id": "ai_overview",
            "name": "AI 概述",
            "type": "concept",
            "description": "人工智能的定义、发展历程、核心分支（ML/DL/NLP/CV）及典型应用场景",
            "difficulty": 1,
            "category": "基础",
            "doc": "01-ai-overview.md",
            "mastery": 0.9,
            "status": "mastered",
            "color": {"bg": "#C8DFF5", "border": "#4A8EC4", "label": "熟练掌握"},
        }

    def test_a02_get_graph_failure_returns_500(self, client):
        """KG-A02: GraphService.get_graph 抛错 → 500（收窄前后同一注入点）。"""
        with _fresh_graph_service(), _boom_method(GraphService, "get_graph"):
            r = client.post("/internal/knowledge-graph/ai_intro", json={"masteries": {}})

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "获取知识图谱失败",
        }

    def test_a03_node_card_success(self, client):
        """KG-A03: 节点卡片四段结构 + 子段键序。"""
        with _fresh_graph_service():
            r = client.post(
                "/internal/knowledge-graph/ai_intro/node/ai_overview",
                json={"masteries": {}, "total_exercises": 3},
            )

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == ["node", "performance", "graph_context", "actions"]
        assert data["node"]["id"] == "ai_overview"
        assert list(data["node"].keys()) == GRAPH_NODE_KEYS
        assert list(data["performance"].keys()) == [
            "sub_concepts", "total_exercises", "last_practiced",
        ]
        assert data["performance"]["total_exercises"] == 3
        assert data["performance"]["last_practiced"] is None
        assert len(data["performance"]["sub_concepts"]) == 3
        assert list(data["graph_context"].keys()) == [
            "prerequisites", "unlocks", "related",
        ]
        assert data["graph_context"]["prerequisites"] == []
        assert list(data["graph_context"]["unlocks"][0].keys()) == [
            "id", "name", "status", "mastery", "color",
        ]
        assert data["actions"] == [
            {"label": "开始学习", "type": "primary", "target": "resource"},
        ]

    def test_a04_node_card_missing_node_returns_404(self, client):
        """KG-A04: 节点不存在 → 404（ValueError 映射，文案是固定串不是 str(e)）。"""
        with _fresh_graph_service():
            r = client.post(
                "/internal/knowledge-graph/ai_intro/node/nope",
                json={"masteries": {}},
            )

        assert r.status_code == 404
        assert r.json() == {
            "success": False, "errorCode": "NOT_FOUND", "error": "节点不存在",
        }

    def test_a05_node_card_failure_returns_500(self, client):
        """KG-A05: 非 ValueError 异常 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "get_node_card"):
            r = client.post(
                "/internal/knowledge-graph/ai_intro/node/ai_overview",
                json={"masteries": {}},
            )

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "获取节点卡片失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — /graph/extract（KG-A06..A07）
# ═══════════════════════════════════════════════════════════════════

class TestGraphExtract:

    def test_a06_extract_success_four_keys_in_order(self, client):
        """KG-A06: 抽取结果四键组装且顺序固定。"""
        groups = {
            "primary": [{"node_id": "p1"}],
            "related": [{"node_id": "r1"}],
            "broad": [{"node_id": "b1"}],
            "all": [{"node_id": "p1"}, {"node_id": "r1"}, {"node_id": "b1"}],
        }
        with _fresh_graph_service(), _stub_extraction(groups) as calls:
            r = client.post("/internal/graph/extract", json={
                "course_id": "ai_intro",
                "user_message": "什么是过拟合",
                "assistant_reply": "过拟合指模型在训练集上表现过好",
                "existing_node_ids": ["backprop"],
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == ["primary", "related", "broad", "candidates"]
        assert data["primary"] == [{"node_id": "p1"}]
        assert data["related"] == [{"node_id": "r1"}]
        assert data["broad"] == [{"node_id": "b1"}]
        assert data["candidates"] == groups["all"]  # "all" 重命名为 "candidates"
        assert calls == [{
            "course_id": "ai_intro",
            "user_message": "什么是过拟合",
            "assistant_reply": "过拟合指模型在训练集上表现过好",
            "existing_node_ids": ["backprop"],
        }]

    def test_a07_extract_missing_keys_default_empty(self, client):
        """KG-A07: 抽取结果缺键 → 空列表（`groups.get(k, [])` 语义）。"""
        with _fresh_graph_service(), _stub_extraction({"primary": [{"node_id": "p1"}]}):
            r = client.post("/internal/graph/extract", json={
                "course_id": "ai_intro",
                "user_message": "q",
                "assistant_reply": "a",
            })

        assert r.status_code == 200
        assert r.json()["data"] == {
            "primary": [{"node_id": "p1"}],
            "related": [],
            "broad": [],
            "candidates": [],
        }

    def test_a08_extract_failure_returns_500(self, client):
        """KG-A08: 抽取抛错 → 500 `GENERATION_FAILED`。"""
        async def _raise(**kwargs):
            raise RuntimeError("llm down")

        with _fresh_graph_service(), _patch_extraction(_raise):
            r = client.post("/internal/graph/extract", json={
                "course_id": "ai_intro", "user_message": "q", "assistant_reply": "a",
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False,
            "errorCode": "GENERATION_FAILED",
            "error": "知识节点提取失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — /graph/nodes 批量变更（KG-A09..A12）
# ═══════════════════════════════════════════════════════════════════

class TestGraphNodesMutations:

    def test_a09_add_node_grows_graph(self, client):
        """KG-A09: add_node 后重取图谱 → 新节点在列（内存变异语义）。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_node",
                             "data": {"id": "dyn_x", "name": "动态X", "difficulty": 4}}],
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == GET_GRAPH_DATA_KEYS
        ids = [n["id"] for n in data["nodes"]]
        assert ids[-1] == "dyn_x"
        assert len(ids) == SKELETON_NODE_COUNT + 1
        added = data["nodes"][-1]
        assert list(added.keys()) == ADDED_NODE_KEYS
        assert added["name"] == "动态X"
        assert added["difficulty"] == 4
        assert added["category"] == "其他"  # 默认值
        assert added["status"] == "locked"
        assert added["mastery"] == 0.0

    def test_a10_add_edge_grows_graph(self, client):
        """KG-A10: add_edge 后重取图谱 → 新边插在 parallel 块之前 + 自动补 1 条 parallel。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_edge",
                             "data": {"source": "ai_overview", "target": "cnn"}}],
            })

        assert r.status_code == 200
        edges = r.json()["data"]["edges"]
        assert len(edges) == GRAPH_EDGE_COUNT_AFTER_ONE_ADD
        # 显式边插在 15 条骨架边之后、parallel 块之前（不是 append 到末尾）
        assert edges[15] == {
            "source": "ai_overview", "target": "cnn",
            "relation": "depends_on", "rationale": "",
        }
        assert list(edges[15].keys()) == GRAPH_EDGE_KEYS
        # auto_add_parallel_edges 因 cnn 多了一个前置而补出的新边
        assert edges[16] == {
            "source": "ml_basics", "target": "cnn",
            "relation": "parallel", "rationale": "共同前置: ai_overview",
        }

    def test_a11_multiple_updates_applied_in_order(self, client):
        """KG-A11: updates 列表按序 dispatch（add_node 后 add_edge 能引用新节点）。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [
                    {"action": "add_node", "data": {"id": "dyn_y", "name": "Y"}},
                    {"action": "add_edge",
                     "data": {"source": "ai_overview", "target": "dyn_y"}},
                ],
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert [n["id"] for n in data["nodes"]][-1] == "dyn_y"
        assert len(data["nodes"]) == SKELETON_NODE_COUNT + 1
        assert len(data["edges"]) == GRAPH_EDGE_COUNT_AFTER_ONE_ADD
        assert ("ai_overview", "dyn_y") in [(e["source"], e["target"]) for e in data["edges"]]

    def test_a12_duplicate_node_returns_400_with_message(self, client):
        """KG-A12: ValueError → 400 `INVALID_REQUEST`，文案为 str(e)。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_node", "data": {"id": "ai_overview"}}],
            })

        assert r.status_code == 400
        assert r.json() == {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "节点 'ai_overview' 已存在",
        }

    def test_a13_add_node_failure_returns_500(self, client):
        """KG-A13: 非 ValueError 异常 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "add_node"):
            r = client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_node", "data": {"id": "dyn_z"}}],
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "图谱更新失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — /graph/masteries（KG-A14..A16）
# ═══════════════════════════════════════════════════════════════════

class TestMasteryBatchUpdate:

    def test_a14_masteries_accumulate_over_events(self, client):
        """KG-A14: 已有掌握度上按事件累积（含未出现节点从 0 起算）。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/masteries", json={
                "course_id": "ai_intro",
                "masteries": {"ai_overview": 0.5},
                "events": [
                    {"node_id": "ai_overview", "event_type": "exercise_done", "score": 0.8},
                    {"node_id": "ml_basics", "event_type": "resource_viewed"},
                ],
            })

        assert r.status_code == 200
        assert r.json() == {
            "success": True,
            "data": {"masteries": {"ai_overview": 0.62, "ml_basics": 0.1}},
        }

    def test_a15_empty_events_rejected_by_pydantic_not_route(self, client):
        """KG-A15: `events=[]` 在进路由前就被 Pydantic 拦下。

        路由里那句 `if not body.events: return api_error(...)` 是**不可达死代码**
        （`MasteryUpdateRequest.events` 带 `min_length=1`）。此用例锁定这一事实：
        文案来自 pydantic，不是路由的作者文案「events 不能为空」。
        """
        with _fresh_graph_service():
            r = client.post("/internal/graph/masteries", json={
                "course_id": "ai_intro", "masteries": {}, "events": [],
            })

        assert r.status_code == 400
        body = r.json()
        # 校验异常走的是 `main.py` 的 RequestValidationError 处理器：**snake_case**
        # `error_code`，与路由 api_error 的 camelCase `errorCode` 不同。
        assert list(body.keys()) == ["success", "error", "error_code"]
        assert body["success"] is False
        assert body["error_code"] == "INVALID_REQUEST"
        assert body["error"].startswith("字段 'events' List should have at least 1 item")
        assert "events 不能为空" not in body["error"]

    def test_a16_mastery_failure_propagates_unwrapped(self, client):
        """KG-A16: 该端点**没有 try/except**，内部异常原样上抛（非 api_error 信封）。

        这是图谱域唯一一个例外端点；收窄时必须原样保留，否则异常响应体形状会变。
        """
        def _raise(*args, **kwargs):
            raise RuntimeError("mastery down")

        with _fresh_graph_service(), _patch_method(
            PlanService, "update_mastery", staticmethod(_raise),
        ):
            with pytest.raises(RuntimeError, match="mastery down"):
                client.post("/internal/graph/masteries", json={
                    "course_id": "ai_intro",
                    "masteries": {},
                    "events": [{"node_id": "a", "event_type": "resource_viewed"}],
                })


# ═══════════════════════════════════════════════════════════════════
# Part A — /graph/reload（KG-A17..A18）
# ═══════════════════════════════════════════════════════════════════

class TestGraphReload:

    def test_a17_reload_returns_raw_skeleton_counts(self, client):
        """KG-A17: 返回**原始骨架**计数（15 边，不含 auto parallel 边）。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/reload", json={})

        assert r.status_code == 200
        assert r.text == (
            '{"success":true,"data":{"status":"reloaded","nodes":10,"edges":15}}'
        )

    def test_a18_reload_wipes_runtime_mutations(self, client):
        """KG-A18: reload 抹掉运行时增删（现有内存语义，收窄后必须保持）。"""
        with _fresh_graph_service():
            client.post("/internal/graph/nodes", json={
                "course_id": "ai_intro",
                "updates": [{"action": "add_node", "data": {"id": "dyn_w", "name": "W"}}],
            })
            grown = client.post("/internal/knowledge-graph/ai_intro", json={"masteries": {}})
            assert len(grown.json()["data"]["nodes"]) == SKELETON_NODE_COUNT + 1

            client.post("/internal/graph/reload", json={})
            after = client.post("/internal/knowledge-graph/ai_intro", json={"masteries": {}})

        assert len(after.json()["data"]["nodes"]) == SKELETON_NODE_COUNT

    def test_a19_reload_failure_returns_500(self, client):
        """KG-A19: 骨架加载抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "load_skeleton"):
            r = client.post("/internal/graph/reload", json={})

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "图谱热更新失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — 图谱分析（KG-A20..A25）
# ═══════════════════════════════════════════════════════════════════

class TestGraphAnalysis:

    def test_a20_next_node_success(self, client):
        """KG-A20: 推荐列表信封 + 条目键序。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/next-node", json={
                "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == ["recommended"]
        assert list(data["recommended"][0].keys()) == [
            "node_id", "name", "mastery", "status", "difficulty",
            "category", "readiness", "unmet_prerequisites", "unlocks_count",
        ]
        assert data["recommended"][0]["node_id"] == "ai_overview"

    def test_a21_next_node_failure_returns_500(self, client):
        """KG-A21: 推荐抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "recommend_next_node"):
            r = client.post("/internal/graph/next-node", json={
                "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "节点推荐失败",
        }

    def test_a22_progress_success(self, client):
        """KG-A22: 进度概要键序 + 全锁定初始态。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/progress", json={
                "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == [
            "total_nodes", "mastered_count", "learning_count", "locked_count",
            "global_mastery_pct", "by_category", "by_difficulty", "recommended_focus",
        ]
        assert (data["total_nodes"], data["mastered_count"], data["locked_count"]) == (10, 0, 10)
        assert data["global_mastery_pct"] == 0.0
        assert data["by_category"]["基础"] == {
            "total": 1, "mastered": 0, "learning": 0, "locked": 1, "avg_mastery": 0.0,
        }

    def test_a23_progress_failure_returns_500(self, client):
        """KG-A23: 概要抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "get_progress_summary"):
            r = client.post("/internal/graph/progress", json={
                "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "进度概要获取失败",
        }

    def test_a24_check_prerequisites_success(self, client):
        """KG-A24: 前置检查全字段 + threshold 默认 0.6。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/check-prerequisites", json={
                "node_id": "ml_basics", "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 200
        assert r.json()["data"] == {
            "node_id": "ml_basics",
            "node_name": "机器学习基础",
            "can_learn": False,
            "prerequisites": [
                {"node_id": "ai_overview", "name": "AI 概述", "mastery": 0.0,
                 "met": False, "gap": 0.6},
            ],
            "unmet": [
                {"node_id": "ai_overview", "name": "AI 概述", "mastery": 0.0,
                 "met": False, "gap": 0.6},
            ],
            "met_count": 0,
            "unmet_count": 1,
            "total_prerequisites": 1,
            "threshold": 0.6,
        }

    def test_a25_check_prerequisites_failure_returns_500(self, client):
        """KG-A25: 前置检查抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "check_prerequisites"):
            r = client.post("/internal/graph/check-prerequisites", json={
                "node_id": "ml_basics", "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "前置条件检查失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — 节点维护（KG-A26..A31）
# ═══════════════════════════════════════════════════════════════════

class TestNodeMaintenance:

    def _add_dynamic(self, client, node_id="dyn_m", name="动态M"):
        return client.post("/internal/graph/nodes", json={
            "course_id": "ai_intro",
            "updates": [{"action": "add_node", "data": {"id": node_id, "name": name}}],
        })

    def test_a26_delete_dynamic_node_success(self, client):
        """KG-A26: 删除动态节点 → 返回被删对象 + node_id。"""
        with _fresh_graph_service():
            self._add_dynamic(client)
            r = client.post("/internal/graph/nodes/dyn_m/delete",
                            json={"course_id": "ai_intro"})

        assert r.status_code == 200
        assert r.json()["data"] == {
            "deleted": {
                "id": "dyn_m", "name": "动态M", "type": "concept",
                "description": "", "difficulty": 3, "category": "其他",
            },
            "node_id": "dyn_m",
        }

    def test_a27_delete_skeleton_node_returns_400(self, client):
        """KG-A27: 骨架节点不可删（白名单来自 load_skeleton 初始化）。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes/ai_overview/delete",
                            json={"course_id": "ai_intro"})

        assert r.status_code == 400
        assert r.json() == {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "骨架节点不可删除",
        }

    def test_a28_delete_failure_returns_500(self, client):
        """KG-A28: 删除抛非 ValueError 异常 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "delete_node"):
            r = client.post("/internal/graph/nodes/ai_overview/delete",
                            json={"course_id": "ai_intro"})

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "节点删除失败",
        }

    def test_a29_update_dynamic_node_success(self, client):
        """KG-A29: 动态节点全字段可改。"""
        with _fresh_graph_service():
            self._add_dynamic(client)
            r = client.post("/internal/graph/nodes/dyn_m/update", json={
                "course_id": "ai_intro",
                "updates": {"name": "改名", "difficulty": 9},
            })

        assert r.status_code == 200
        assert r.json()["data"] == {
            "node": {
                "id": "dyn_m", "name": "改名", "type": "concept",
                "description": "", "difficulty": 5, "category": "其他",  # 9 → clamp 到 5
            },
        }

    def test_a30_update_skeleton_node_rejects_field_returns_400(self, client):
        """KG-A30: 骨架节点仅可改 difficulty/category，文案含括注。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/nodes/ai_overview/update", json={
                "course_id": "ai_intro", "updates": {"name": "改名"},
            })

        assert r.status_code == 400
        assert r.json() == {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "节点 'ai_overview' 不允许修改字段 'name'（骨架节点仅可改 difficulty/category）",
        }

    def test_a31_update_failure_returns_500(self, client):
        """KG-A31: 更新抛非 ValueError 异常 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "update_node"):
            r = client.post("/internal/graph/nodes/ai_overview/update", json={
                "course_id": "ai_intro", "updates": {"difficulty": 2},
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "节点更新失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part A — 可视化与补边（KG-A32..A36）
# ═══════════════════════════════════════════════════════════════════

class TestGraphVisualization:

    def test_a32_suggest_edges_success(self, client):
        """KG-A32: 补边建议信封（LLM 注入替身，不触网）。"""
        items = [{"source": "a", "target": "b", "relation": "parallel",
                  "rationale": "r", "confidence": 0.81}]
        with _fresh_graph_service(), _stub_suggest_edges(items) as calls:
            r = client.post("/internal/graph/suggest-edges", json={"course_id": "ai_intro"})

        assert r.status_code == 200
        assert r.text == (
            '{"success":true,"data":{"suggestions":[{"source":"a","target":"b",'
            '"relation":"parallel","rationale":"r","confidence":0.81}]}}'
        )
        assert calls == [{"course_id": "ai_intro"}]

    def test_a33_suggest_edges_failure_returns_500(self, client):
        """KG-A33: 补边抛错 → 500 `GENERATION_FAILED`。"""
        with _fresh_graph_service(), _boom_method(GraphService, "suggest_edges"):
            r = client.post("/internal/graph/suggest-edges", json={"course_id": "ai_intro"})

        assert r.status_code == 500
        assert r.json() == {
            "success": False,
            "errorCode": "GENERATION_FAILED",
            "error": "补边建议生成失败",
        }

    def test_a34_export_mermaid_success(self, client):
        """KG-A34: Mermaid 文本结构（1 头 + 10 节点声明 + 21 边 = 32 行）。

        三种 relation 渲染成三种箭头，故按箭头分别计数而不是总数：
        `depends_on` → `-->`（11 条）、软依赖 → `-.->`（3 条）、
        `parallel` → `===`（7 条）。整串 sha256 存证在 Task 5 的
        `_accept_graph_endpoints.py`。
        """
        with _fresh_graph_service():
            r = client.post("/internal/graph/export-mermaid", json={
                "course_id": "ai_intro", "masteries": {},
            })

        assert r.status_code == 200
        mermaid = r.json()["data"]["mermaid"]
        assert list(r.json()["data"].keys()) == ["mermaid"]
        lines = mermaid.split("\n")
        assert lines[0] == "flowchart TD"
        assert len(lines) == 32
        assert lines[1] == '    ai_overview["AI 概述<br/>未开始 0%"]'
        assert lines[10] == '    cnn["CNN 卷积神经网络<br/>未开始 0%"]'
        assert lines[11] == '    ai_overview -->|"ML 是 AI 的核心方法"| ml_basics'
        assert lines[17] == '    dl_basics -.->|"Transformer 是深度学习在序列建模的延伸"| transformer'
        assert lines[19] == '    overfitting ===|"训练深度网络的两大挑战"| backprop'
        assert mermaid.count("-->") == 11
        assert mermaid.count("-.->") == 3
        assert mermaid.count("===") == 7
        assert 11 + 3 + 7 == GRAPH_EDGE_COUNT_WITH_PARALLEL
        # 末尾**无**换行符（非 POSIX 风格的 `\n`-terminated）
        assert mermaid.endswith('overfitting ===|"共同前置: ml_basics"| gradient_variants')

    def test_a35_export_mermaid_failure_returns_500(self, client):
        """KG-A35: Mermaid 导出抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "export_mermaid"):
            r = client.post("/internal/graph/export-mermaid", json={
                "course_id": "ai_intro", "masteries": {},
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "Mermaid 导出失败",
        }

    def test_a36_layered_success(self, client):
        """KG-A36: 分层图谱多出 layer/layers/max_layer 三段。"""
        with _fresh_graph_service():
            r = client.post("/internal/graph/layered", json={
                "masteries": {"ai_overview": 0.9}, "course_id": "ai_intro",
            })

        assert r.status_code == 200
        data = r.json()["data"]
        assert list(data.keys()) == ["nodes", "edges", "layers", "max_layer"]
        assert len(data["nodes"]) == SKELETON_NODE_COUNT
        assert list(data["nodes"][0].keys()) == GRAPH_NODE_KEYS + ["layer"]
        assert data["nodes"][0]["layer"] == 0
        assert data["nodes"][0]["mastery"] == 0.9
        assert isinstance(data["layers"], list)
        assert isinstance(data["max_layer"], int)

    def test_a37_layered_failure_returns_500(self, client):
        """KG-A37: 分层图谱抛错 → 500。"""
        with _fresh_graph_service(), _boom_method(GraphService, "get_layered_graph"):
            r = client.post("/internal/graph/layered", json={
                "masteries": {}, "course_id": "ai_intro",
            })

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "分层图谱获取失败",
        }

    def test_a38_api_success_failure_returns_500(self, client):
        """KG-A38: `api_success` 抛错 → 500（收窄前后同一注入点，锁 try 包裹范围）。"""
        with _fresh_graph_service(), _boom_success():
            r = client.post("/internal/graph/reload", json={})

        assert r.status_code == 500
        assert r.json() == {
            "success": False, "errorCode": "INTERNAL_ERROR", "error": "图谱热更新失败",
        }


# ═══════════════════════════════════════════════════════════════════
# Part B — GraphCenter 契约（KG-B01..B15，Task 2/3 前 RED）
# ═══════════════════════════════════════════════════════════════════
#
# 全部使用独立实例 `GraphCenter(graph_service=GraphService())`，
# 不碰模块单例，因此用例间零耦合。


def _graph_center_cls():
    """Part B 专用：GraphCenter 落地前抛出可读的 RED 错误（Task 2/3 后转绿）。"""
    try:
        from app.centers.graph_center import GraphCenter
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            "module 'app.centers.graph_center' has no attribute 'GraphCenter'"
            f" — Task 2/3 尚未落地（{exc}）"
        ) from exc
    return GraphCenter


def _center(**over):
    kwargs = {"graph_service": GraphService()}
    kwargs.update(over)
    return _graph_center_cls()(**kwargs)


class TestGraphCenterReadEntries:

    @pytest.mark.asyncio
    async def test_b01_get_graph_passes_course_and_masteries(self):
        """KG-B01: course_id / masteries 透传。"""
        center = _center()
        out = await center.get_graph(course_id="ai_intro", masteries={"ai_overview": 0.9})
        assert list(out.keys()) == GET_GRAPH_DATA_KEYS
        assert out["course_id"] == "ai_intro"
        assert out["nodes"][0]["mastery"] == 0.9

    @pytest.mark.asyncio
    async def test_b02_get_node_card_passes_all_params(self):
        """KG-B02: 五个参数全部透传。"""
        center = _center()
        out = await center.get_node_card(
            course_id="ai_intro", node_id="ai_overview",
            masteries={"ai_overview": 0.4}, total_exercises=7,
            last_practiced="2026-09-01T00:00:00Z",
        )
        assert list(out.keys()) == ["node", "performance", "graph_context", "actions"]
        assert out["node"]["mastery"] == 0.4
        assert out["performance"]["total_exercises"] == 7
        assert out["performance"]["last_practiced"] == "2026-09-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_b03_get_node_card_raises_value_error(self):
        """KG-B03: 节点不存在时**原样抛 ValueError**（错误类型锁定，供 API 映射 404）。"""
        center = _center()
        with pytest.raises(ValueError, match="节点 'nope' 不存在"):
            await center.get_node_card(
                course_id="ai_intro", node_id="nope", masteries={},
                total_exercises=0, last_practiced=None,
            )

    @pytest.mark.asyncio
    async def test_b04_recommend_next_node_wraps_recommended(self):
        """KG-B04: 信封键 `recommended` 由 Center 组装。"""
        center = _center()
        out = await center.recommend_next_node(course_id="ai_intro", masteries={})
        assert list(out.keys()) == ["recommended"]
        assert out["recommended"][0]["node_id"] == "ai_overview"

    @pytest.mark.asyncio
    async def test_b05_progress_summary_passthrough(self):
        """KG-B05: 进度概要直传（不加信封）。"""
        center = _center()
        out = await center.progress_summary(course_id="ai_intro", masteries={})
        assert out["total_nodes"] == SKELETON_NODE_COUNT
        assert out["locked_count"] == 10

    @pytest.mark.asyncio
    async def test_b06_check_prerequisites_passes_threshold(self):
        """KG-B06: threshold / course_id 透传。"""
        center = _center()
        out = await center.check_prerequisites(
            course_id="ai_intro", node_id="ml_basics",
            masteries={"ai_overview": 0.9}, threshold=0.5,
        )
        assert out["threshold"] == 0.5
        assert out["can_learn"] is True
        assert out["unmet_count"] == 0

    @pytest.mark.asyncio
    async def test_b07_export_mermaid_wraps_mermaid(self):
        """KG-B07: 信封键 `mermaid` 由 Center 组装。"""
        center = _center()
        out = await center.export_mermaid(course_id="ai_intro", masteries={})
        assert list(out.keys()) == ["mermaid"]
        assert out["mermaid"].startswith("flowchart TD\n")

    @pytest.mark.asyncio
    async def test_b08_layered_graph_passthrough(self):
        """KG-B08: 分层图谱直传。"""
        center = _center()
        out = await center.layered_graph(course_id="ai_intro", masteries={})
        assert list(out.keys()) == ["nodes", "edges", "layers", "max_layer"]

    @pytest.mark.asyncio
    async def test_b09_suggest_edges_wraps_suggestions(self):
        """KG-B09: 信封键 `suggestions` 由 Center 组装。"""
        center = _center()
        items = [{"source": "a", "target": "b", "relation": "parallel"}]
        with _stub_suggest_edges(items) as calls:
            out = await center.suggest_edges(course_id="ai_intro")

        assert out == {"suggestions": items}
        assert calls == [{"course_id": "ai_intro"}]


class TestGraphCenterWriteEntries:

    @pytest.mark.asyncio
    async def test_b10_apply_updates_dispatches_by_action(self):
        """KG-B10: add_node / add_edge 分别命中，最后重取图谱。"""
        center = _center()
        out = await center.apply_updates(course_id="ai_intro", updates=[
            {"action": "add_node", "data": {"id": "dyn_c", "name": "C"}},
            {"action": "add_edge", "data": {"source": "ai_overview", "target": "dyn_c"}},
        ])
        assert list(out.keys()) == GET_GRAPH_DATA_KEYS
        assert "dyn_c" in [n["id"] for n in out["nodes"]]
        assert len(out["edges"]) == GRAPH_EDGE_COUNT_AFTER_ONE_ADD

    @pytest.mark.asyncio
    async def test_b11_apply_updates_propagates_value_error(self):
        """KG-B11: 非法输入原样抛 ValueError（供 API 映射 400）。"""
        center = _center()
        with pytest.raises(ValueError, match="节点 'ai_overview' 已存在"):
            await center.apply_updates(course_id="ai_intro", updates=[
                {"action": "add_node", "data": {"id": "ai_overview"}},
            ])

    @pytest.mark.asyncio
    async def test_b12_update_masteries_uses_injected_plan_service(self):
        """KG-B12: 累积公式经注入的 plan_service，参数逐次锁定。"""
        calls: list[tuple] = []

        class _SpyPlan:
            @staticmethod
            def update_mastery(current, event_type, score=None):
                calls.append((current, event_type, score))
                return round(current + 0.1, 4)

        center = _center(plan_service=_SpyPlan)
        out = await center.update_masteries(
            course_id="ai_intro",
            masteries={"a": 0.5},
            events=[
                {"node_id": "a", "event_type": "exercise_done", "score": 0.8},
                {"node_id": "a", "event_type": "resource_viewed"},
                {"node_id": "b", "event_type": "exercise_failed"},
            ],
        )

        # 替身返回 current + 0.1：a 0.5→0.6→0.7，b 0.0→0.1
        assert out == {"masteries": {"a": 0.7, "b": 0.1}}
        assert calls == [
            (0.5, "exercise_done", 0.8),
            (0.6, "resource_viewed", None),
            (0.0, "exercise_failed", None),
        ]

    @pytest.mark.asyncio
    async def test_b13_update_masteries_defaults_to_plan_service(self):
        """KG-B13: 不注入时走真实 PlanService（公式端到端一致）。"""
        center = _center()
        out = await center.update_masteries(
            course_id="ai_intro",
            masteries={"ai_overview": 0.5},
            events=[{"node_id": "ai_overview", "event_type": "exercise_done", "score": 0.8}],
        )
        assert out == {"masteries": {"ai_overview": 0.62}}

    @pytest.mark.asyncio
    async def test_b14_reload_skeleton_returns_raw_counts_and_forces(self):
        """KG-B14: `force_reload=True` 且计数取自**原始骨架**。"""
        seen: list[bool] = []
        original = GraphService.load_skeleton

        def _spy(self, force_reload=False):
            seen.append(force_reload)
            return original(self, force_reload=force_reload)

        service = GraphService()
        service.add_node("ai_intro", {"id": "dyn_r", "name": "R"})
        center = _center(graph_service=service)

        with _patch_method(GraphService, "load_skeleton", _spy):
            out = await center.reload_skeleton()

        assert seen == [True]
        assert out == {
            "status": "reloaded",
            "nodes": SKELETON_NODE_COUNT,
            "edges": SKELETON_EDGE_COUNT,
        }

    @pytest.mark.asyncio
    async def test_b15_delete_node_wraps_deleted_and_id(self):
        """KG-B15: 信封 `{deleted, node_id}`；骨架节点抛 ValueError。"""
        center = _center()
        await center.apply_updates(course_id="ai_intro", updates=[
            {"action": "add_node", "data": {"id": "dyn_d", "name": "D"}},
        ])
        out = await center.delete_node(course_id="ai_intro", node_id="dyn_d")
        assert list(out.keys()) == ["deleted", "node_id"]
        assert out["deleted"]["id"] == "dyn_d"
        assert out["node_id"] == "dyn_d"

        with pytest.raises(ValueError, match="骨架节点不可删除"):
            await center.delete_node(course_id="ai_intro", node_id="ai_overview")

    @pytest.mark.asyncio
    async def test_b16_update_node_wraps_node(self):
        """KG-B16: 信封 `{node}`；非法字段抛 ValueError。"""
        center = _center()
        await center.apply_updates(course_id="ai_intro", updates=[
            {"action": "add_node", "data": {"id": "dyn_u", "name": "U"}},
        ])
        out = await center.update_node(
            course_id="ai_intro", node_id="dyn_u", updates={"name": "改名"},
        )
        assert list(out.keys()) == ["node"]
        assert out["node"]["name"] == "改名"

        with pytest.raises(ValueError, match="不允许修改字段"):
            await center.update_node(
                course_id="ai_intro", node_id="ai_overview", updates={"name": "X"},
            )

    @pytest.mark.asyncio
    async def test_b17_extract_nodes_builds_four_keys(self):
        """KG-B17: 抽取入口四键组装 + `all` → `candidates` 重命名 + 参数透传。"""
        groups = {
            "primary": [{"node_id": "p1"}],
            "related": [{"node_id": "r1"}],
            "broad": [{"node_id": "b1"}],
            "all": [{"node_id": "p1"}, {"node_id": "r1"}, {"node_id": "b1"}],
        }
        calls: list[dict] = []

        async def _fake(*, course_id, user_message, assistant_reply, existing_node_ids=None):
            calls.append({
                "course_id": course_id,
                "user_message": user_message,
                "assistant_reply": assistant_reply,
                "existing_node_ids": existing_node_ids,
            })
            return groups

        center = _center(extraction=_fake)
        out = await center.extract_nodes(
            course_id="ai_intro", user_message="q", assistant_reply="a",
            existing_node_ids=["backprop"],
        )

        assert list(out.keys()) == ["primary", "related", "broad", "candidates"]
        assert out["candidates"] == groups["all"]
        assert calls == [{
            "course_id": "ai_intro", "user_message": "q",
            "assistant_reply": "a", "existing_node_ids": ["backprop"],
        }]
