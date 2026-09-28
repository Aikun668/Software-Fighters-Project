"""P2 Task 3 契约测试：`LearningSnapshot` 只读读模型（P1 §二）。

对应验收项（P1 §6.3）：
- **A3**：无记录节点的 `mastery.value == null` 且 `level == not_started`（**非 0.5**）。
- **A8**：`freshness.computed_from` 如实反映缺失来源。

同时冻结：
1. `POST /internal/snapshot` 的对外形状与错误信封（与 `/evidence/apply` 同风格）；
2. §2.2 `current_node.reason` 的四级冻结优先级；
3. §二 **读模型性质** —— 只读、可追溯、带来源，**不得静默修改计划或掌握度**。

「只读」在测试里的可执行化：请求前后回显的 `plan` / `steps` / `masteries` 必须逐字节相等
（`_echo_payload`）。这比断言「没写库」更硬 —— 纯函数根本无从修改调用方的字典。
"""

import copy
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import internal_api
from app.centers.graph_center import GraphCenter
from app.services.graph_service import GraphService


SNAPSHOT_URL = "/internal/snapshot"


def _format_validation_error(exc: RequestValidationError) -> str:
    """与既有契约测试保持一致：`字段 '{field}' {msg}`。"""
    parts = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        field = ".".join(loc) or "(root)"
        parts.append(f"字段 '{field}' {err.get('msg', '')}")
    return "; ".join(parts)


class _RecordingCenter:
    """记录每次委派后转交真实 `GraphCenter`（沿用 test_graph_endpoints_api_delegation 手法）。

    链路本身仍走真实 Center，因此测试对「图谱取数签名」的耦合是真实的。
    """

    def __init__(self, real, calls: list[tuple[str, dict]]):
        self._real = real
        self._calls = calls

    async def get_graph(self, **kwargs):
        self._calls.append(("get_graph", kwargs))
        return await self._real.get_graph(**kwargs)

    async def recommend_next_node(self, **kwargs):
        self._calls.append(("recommend_next_node", kwargs))
        return await self._real.recommend_next_node(**kwargs)


class _BoomCenter:
    """图谱域整体不可用：两个取数入口都抛异常。"""

    async def get_graph(self, **kwargs):
        raise RuntimeError("graph service down")

    async def recommend_next_node(self, **kwargs):
        raise RuntimeError("graph service down")


@pytest.fixture()
def graph_calls() -> list[tuple[str, dict]]:
    return []


@pytest.fixture()
def client(graph_calls, monkeypatch) -> TestClient:
    """真实路由 + 记录式 GraphCenter（真实链路，图谱取数可观测）。"""
    real = GraphCenter(graph_service=GraphService())
    monkeypatch.setattr(
        internal_api, "_graph_center_singleton", _RecordingCenter(real, graph_calls),
    )

    app = FastAPI()
    app.include_router(internal_api.router)

    @app.exception_handler(RequestValidationError)
    async def _handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "errorCode": "INVALID_REQUEST",
                "error": _format_validation_error(exc),
            },
        )

    return TestClient(app)


@pytest.fixture()
def broken_graph_client(monkeypatch) -> TestClient:
    """图谱域不可用（两个入口都抛）——用于验证降级而非 500。"""
    monkeypatch.setattr(internal_api, "_graph_center_singleton", _BoomCenter())

    app = FastAPI()
    app.include_router(internal_api.router)
    return TestClient(app)


def _payload(**overrides) -> dict:
    base = {
        "student_id": 7,
        "course_id": "ai_intro",
        "plan": {},
        "steps": [],
        "masteries": {},
        "recent_evidence": [],
        "student_profile": {},
        "recent_records": [],
        "session_analysis": {},
    }
    base.update(overrides)
    return base


def _plan(**overrides) -> dict:
    """默认计划：**相对当下**的活跃计划（空闲 0 天）→ 恒不 `interrupted`。

    刻意不写死日历日：`_plan()` 被大量断言 `stale is False` 的用例复用，
    写死会让测试在若干天后自行失效（日期炸弹）。
    需要「中断」的场景请显式覆盖 `status="paused"` 或把 `last_activity_at` 推远。
    """
    active_at = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    base = {"id": 42, "title": "AI 入门 30 天", "status": "in_progress",
            "last_activity_at": active_at}
    base.update(overrides)
    return base


def _long_ago(days: int = 200) -> str:
    """距当下 N 天的时刻（用于「已远超复习间隔」的终态步骤）。"""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _step(**overrides) -> dict:
    base = {
        "id": 1, "step_order": 1, "topic": "机器学习基础",
        "knowledge_node_id": "ml_basics", "status": "in_progress",
        "mastery_current": None, "mastery_after": None,
    }
    base.update(overrides)
    return base


def _evidence(**overrides) -> dict:
    base = {
        "evidence_id": "exercise:1001:ml_basics",
        "student_id": 7,
        "course_id": "ai_intro",
        "node_id": "ml_basics",
        "type": "exercise_done",
        "occurred_at": "2026-09-27T20:00:00+08:00",
        "source_action": "exercise",
        "source_record_id": "1001",
        "score_or_result": 1.0,
        "confidence": None,
        "effect_hint": "exercise_done",
        "explanation": "学生在练习域完成第 1001 题并答对",
    }
    base.update(overrides)
    return base


def _echo_payload(resp) -> dict:
    """回显请求体（用于「只读」断言：路由不得改动调用方传入的任何结构）。"""
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


# ═══════════════════════════════════════════════════════════════════
# Part 1 —— A3：无记录 = 未学习，value 为 null（不是 0.5）
# ═══════════════════════════════════════════════════════════════════


class TestMasteryNoRecord:

    @pytest.mark.asyncio
    async def test_snap_a03_no_record_yields_null_value_not_half(self, client):
        """A3 核心：`node_masteries` 无该键、计划内也无快照 → `value is None`。

        旧口径把无记录当 `0.5` 兜底（P1 §3.5 已判错）。`null` 与 `0.0` 在 level 上
        合并为 `not_started`，但在 value 上必须保持可区分。
        """
        resp = client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={},
        ))
        data = _echo_payload(resp)
        assert data["current_node"]["node_id"] == "ml_basics"
        assert data["mastery"]["node_id"] == "ml_basics"
        assert data["mastery"]["value"] is None
        assert data["mastery"]["level"] == "not_started"
        assert data["mastery"]["source"] == "none"

    @pytest.mark.asyncio
    async def test_snap_a03_zero_and_null_stay_distinct_in_value(self, client):
        """`0.0`（学了但未成型）与 `null`（无记录）level 相同，value 必须不同。"""
        zero = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.0},
        )))
        assert zero["mastery"]["value"] == 0.0
        assert zero["mastery"]["level"] == "not_started"

        null = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={},
        )))
        assert null["mastery"]["value"] is None
        assert null["mastery"]["level"] == "not_started"
        assert zero["mastery"]["value"] != null["mastery"]["value"]

    @pytest.mark.asyncio
    async def test_snap_a03_plan_snapshot_is_only_a_degraded_source(self, client):
        """计划内快照（`mastery_current`）只在主源缺该键时降级生效，并如实标注来源。"""
        resp = client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step(mastery_current=0.45)], masteries={},
        ))
        data = _echo_payload(resp)
        assert data["mastery"]["value"] == 0.45
        assert data["mastery"]["source"] == "plan_step_snapshot"
        assert data["freshness"]["stale"] is True

    @pytest.mark.asyncio
    async def test_snap_a03_node_masteries_wins_over_step_snapshot(self, client):
        """主源优先：`node_masteries` 有该键时，计划内快照不参与（P1 §3.3）。"""
        resp = client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step(mastery_current=0.45)], masteries={"ml_basics": 0.7},
        ))
        data = _echo_payload(resp)
        assert data["mastery"]["value"] == 0.7
        assert data["mastery"]["source"] == "node_masteries"
        assert data["freshness"]["stale"] is False

    @pytest.mark.asyncio
    async def test_snap_a03_level_bands_come_from_single_source(self, client):
        """五级 level 必须由 `mastery_scale` 唯一真源给出，读模型不得自行分档。

        期望值**硬编码**而非调用 `mastery_to_level` 对拍：否则实现与测试共用同一函数，
        两边一起漂移也照样绿（同源对拍抓不到口径漂移）。边界值取五档的
        下界与下界前一档，确保 `level` 是读模型如实转交真源的结果。
        """
        expected = {
            0.0: "not_started", 0.29: "beginner", 0.3: "learning",
            0.59: "learning", 0.6: "proficient", 0.84: "proficient",
            0.85: "mastered", 1.0: "mastered",
        }
        for mastery, level in expected.items():
            resp = client.post(SNAPSHOT_URL, json=_payload(
                plan=_plan(), steps=[_step()], masteries={"ml_basics": mastery},
            ))
            data = _echo_payload(resp)
            assert data["mastery"]["value"] == mastery
            assert data["mastery"]["level"] == level, f"mastery={mastery} 分档漂移"

    @pytest.mark.asyncio
    async def test_snap_bool_mastery_is_not_coerced_to_number(self):
        """bool 是 int 子类：读模型不得把它静默当成 1.0/0.0（与 evidence_contract 同口径）。

        经 HTTP 边界时 Pydantic 会把 `True` 按 `dict[str, float]` 归一为 `1.0`，
        因此这里直接调用纯函数，验证 `_build_mastery` **自身**的 bool 守卫。
        """
        from app.services import learning_snapshot

        result = learning_snapshot.build_snapshot(
            student_id=7, course_id="ai_intro",
            plan=_plan(), steps=[_step()],
            masteries={"ml_basics": True},
            recent_evidence=[], student_profile={},
            recent_records=[], session_analysis={},
            graph_nodes=[{"id": "ml_basics", "name": "机器学习基础"}],
        )
        assert result["mastery"]["value"] is None
        assert result["mastery"]["source"] == "none"


# ═══════════════════════════════════════════════════════════════════
# Part 2 —— A8：freshness.computed_from 如实反映缺失来源
# ═══════════════════════════════════════════════════════════════════


class TestFreshness:

    @pytest.mark.asyncio
    async def test_snap_a08_all_sources_present(self, client):
        resp = client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
            student_profile={"preferred_style": "visual"},
        ))
        data = _echo_payload(resp)
        assert data["freshness"]["computed_from"] == ["active_plan", "mastery", "profile", "graph"]
        assert data["freshness"]["missing_sources"] == []

    @pytest.mark.asyncio
    async def test_snap_a08_missing_profile_is_reported(self, client):
        """无画像输入 → `profile` 必须落进 missing_sources，且不计入 computed_from。"""
        resp = client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        ))
        data = _echo_payload(resp)
        assert data["freshness"]["computed_from"] == ["active_plan", "mastery", "graph"]
        assert data["freshness"]["missing_sources"] == ["profile"]
        assert data["profile_context"] is None

    @pytest.mark.asyncio
    async def test_snap_a08_empty_request_reports_every_source_missing(self, client):
        """最小请求：仅图谱可用 → 其余三项全部如实缺失。"""
        resp = client.post(SNAPSHOT_URL, json=_payload())
        data = _echo_payload(resp)
        assert data["freshness"]["computed_from"] == ["graph"]
        assert data["freshness"]["missing_sources"] == ["active_plan", "mastery", "profile"]

    @pytest.mark.asyncio
    async def test_snap_a08_order_is_frozen(self, client):
        """`computed_from` 顺序固定，便于契约测试与人工审计。"""
        order = ["active_plan", "mastery", "profile", "graph"]
        for overrides in (
            {},
            {"plan": _plan()},
            {"plan": _plan(), "masteries": {"ml_basics": 0.2}},
            {"masteries": {"ml_basics": 0.2}},
        ):
            data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(**overrides)))
            got = data["freshness"]["computed_from"]
            assert got == [s for s in order if s in got], f"顺序漂移：{got}"

    @pytest.mark.asyncio
    async def test_snap_a08_broken_graph_degrades_but_truthfully(self, broken_graph_client):
        """图谱域整体不可用 → 降级为「无图谱」而非 500，且如实报告 graph 缺失。

        P1 §二 允许 `current_node` 为 null，§2.6 的 `missing_sources` 存在的意义正是
        标注这种缺口。若此处 500，会把可用的 `active_plan`/`mastery`/`recent_evidence`
        一并丢掉 —— 那是把「富化失败」升级成了「读模型不可用」。
        """
        resp = broken_graph_client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        ))
        assert resp.status_code == 200, resp.text
        data = _echo_payload(resp)
        assert "graph" in data["freshness"]["missing_sources"]
        assert "graph" not in data["freshness"]["computed_from"]
        # 其余来源照常可用 —— 证明降级是局部的
        assert data["mastery"]["value"] == 0.4
        assert data["active_plan"] is not None

    @pytest.mark.asyncio
    async def test_snap_interrupted_plan_marks_stale(self, client):
        """paused / 空闲超 7 天 → interrupted，且 freshness.stale 如实置位（P2 D1）。"""
        stale_plan = _plan(status="paused")
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=stale_plan, steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert data["active_plan"]["interrupted"] is True
        assert data["freshness"]["stale"] is True

        idle_plan = _plan(last_activity_at=_long_ago(120))
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=idle_plan, steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert data["active_plan"]["interrupted"] is True

    @pytest.mark.asyncio
    async def test_snap_unparsable_last_activity_is_not_interrupted(self, client):
        """时间戳缺失/不可解析 → 不误判为中断（宁可乐观，不要凭空 stale）。"""
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(last_activity_at=None), steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert data["active_plan"]["interrupted"] is False
        assert data["freshness"]["stale"] is False


# ═══════════════════════════════════════════════════════════════════
# Part 3 —— §二 性质：只读、零副作用
# ═══════════════════════════════════════════════════════════════════


class TestReadOnlyNature:

    @pytest.mark.asyncio
    async def test_snap_does_not_mutate_request_context(self, client):
        """只读性质的硬断言：读模型不得静默修改计划或掌握度（P1 §二 性质）。

        纯函数无从改写调用方的对象；此处用深拷贝快照比对，任何就地写入都会露馅。
        """
        payload = _payload(
            plan=_plan(extra_ignored_key="x"),
            steps=[_step(), _step(id=2, step_order=2, knowledge_node_id="dl_basics",
                                 status="completed", last_review_at=_long_ago(200),
                                 mastery_current=0.6, topic_difficulty=3, review_count=0)],
            masteries={"ml_basics": 0.33, "ai_overview": 0.9},
            recent_evidence=[_evidence()],
            student_profile={"weak_points": ["正则化"], "preferred_style": "visual"},
        )
        before = copy.deepcopy(payload)

        assert client.post(SNAPSHOT_URL, json=payload).status_code == 200
        assert payload == before, "请求体被就地修改 —— 违反只读性质"

    @pytest.mark.asyncio
    async def test_snap_next_action_populated_by_task4(self, client):
        """Task 4 落地后 `next_action` 不再是 null。

        本载荷：当前步骤节点 `ml_basics`（`reason=current_step_node`）+ `mastery.level`
        = `learning` → 命中 P1 §5.3 行 2「该复习了」→ `review_current_node`。
        键的存在性由 `test_snap_contract_key_set_is_frozen` 继续冻结。
        """
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert "next_action" in data
        assert data["next_action"] is not None
        assert data["next_action"]["action_kind"] == "review_current_node"

    @pytest.mark.asyncio
    async def test_snap_contract_key_set_is_frozen(self, client):
        """10 个顶层键冻结；新增字段必须显式改本断言（防悄悄漂移）。"""
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(plan=_plan(), steps=[_step()])))
        assert set(data) == {
            "student_id", "course_id", "generated_at", "active_plan", "current_node",
            "mastery", "recent_evidence", "profile_context", "freshness", "next_action",
        }
        assert set(data["mastery"]) == {"node_id", "value", "level", "source", "last_evidence_at"}
        assert set(data["freshness"]) == {"stale", "missing_sources", "computed_from"}

    @pytest.mark.asyncio
    async def test_snap_graph_is_fetched_from_request_body_context(self, client, graph_calls):
        """图谱数据不进请求体，由路由层用请求体上下文补齐（P2 §五 边界规则 1）。"""
        client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        ))
        methods = [name for name, _ in graph_calls]
        assert methods == ["get_graph", "recommend_next_node"]
        for _, kwargs in graph_calls:
            assert kwargs["course_id"] == "ai_intro"
            assert kwargs["masteries"] == {"ml_basics": 0.4}


# ═══════════════════════════════════════════════════════════════════
# Part 4 —— §2.1 / §2.2 / §2.4 / §2.5 读模型各段
# ═══════════════════════════════════════════════════════════════════


class TestCurrentNodePriority:

    @pytest.mark.asyncio
    async def test_snap_priority_1_current_step_node(self, client):
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ai_overview": 0.2},
        )))
        assert data["current_node"] == {
            "node_id": "ml_basics", "name": "机器学习基础", "reason": "current_step_node",
        }

    @pytest.mark.asyncio
    async def test_snap_priority_2_review_due(self, client):
        """无进行中步骤时，已过复习窗口的终态节点优先于最薄弱节点。"""
        review_step = _step(
            id=9, step_order=1, knowledge_node_id="dl_basics", status="completed",
            last_review_at=_long_ago(200),
            mastery_current=0.6, topic_difficulty=3, review_count=0,
        )
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan={}, steps=[review_step], masteries={"ml_basics": 0.05},
        )))
        assert data["current_node"]["node_id"] == "dl_basics"
        assert data["current_node"]["reason"] == "review_due"

    @pytest.mark.asyncio
    async def test_snap_review_due_gates_on_interval_and_decay(self, client):
        """`review_due` 是**合取**闸门，两道各自可断。

        - 间隔闸门：`days_since < interval` → 刚复习过，不算到期（**本读模型特有**，
          `get_review_schedule` 无此道，见 `learning_snapshot._review_due_candidates` docstring）；
        - 衰减闸门：`decayed >= REVIEW_DECAY_FLOOR` → 还记得，不算到期（与 plan_service 同源）。
        日期与掌握度都由 `PlanService` 公式反推，不写死日历日。
        """
        from app.services.plan_service import PlanService

        assert PlanService.get_half_life(3, 0) == 7.0  # 公式真源，防实现漂移
        now = datetime.now(timezone.utc)

        # 闸门 A：间隔未到（days_since=0 < interval=1）
        gate_a = _step(
            id=9, step_order=1, knowledge_node_id="dl_basics", status="completed",
            last_review_at=now.isoformat(),
            mastery_current=0.6, topic_difficulty=3, review_count=0,
        )
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan={}, steps=[gate_a], masteries={"ml_basics": 0.05},
        )))
        assert data["current_node"]["node_id"] == "ml_basics"
        assert data["current_node"]["reason"] == "weakest"

        # 闸门 B：间隔已过（days_since=1 >= interval=1），但掌握度仍高、衰减未到阈值
        assert PlanService.estimate_decay(0.9, 1, 3, 0) >= 0.7, "前提失效：衰减已低于阈值"
        gate_b = _step(
            id=9, step_order=1, knowledge_node_id="dl_basics", status="completed",
            last_review_at=(now - timedelta(days=1)).isoformat(),
            mastery_current=0.9, topic_difficulty=3, review_count=0,
        )
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan={}, steps=[gate_b], masteries={"ml_basics": 0.05},
        )))
        assert data["current_node"]["node_id"] == "ml_basics"
        assert data["current_node"]["reason"] == "weakest"

    @pytest.mark.asyncio
    async def test_snap_priority_3_weakest(self, client):
        """`<= 0` 视为未学习，不进 weakest 候选（P1 §3.5）。"""
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            masteries={"ml_basics": 0.0, "dl_basics": 0.12, "ai_overview": 0.66},
        )))
        assert data["current_node"]["node_id"] == "dl_basics"
        assert data["current_node"]["reason"] == "weakest"

    @pytest.mark.asyncio
    async def test_snap_priority_4_next_ready(self, client):
        """无计划/无复习/无薄弱 → 复用图为推荐的 next_ready。

        `masteries` 留空是关键：任何 `> 0` 的记录都会被 `_weakest_node` 抢走。
        """
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            masteries={},
        )))
        assert data["current_node"]["reason"] == "next_ready"
        assert data["current_node"]["node_id"] == "ai_overview"  # 唯一根节点，先修已满足
        assert data["current_node"]["name"]

    @pytest.mark.asyncio
    async def test_snap_all_blank_in_graph_outage_yields_null_current_node(self, broken_graph_client):
        """四路全落空（图谱也不可用）→ `current_node` 为 null，而不是报错。"""
        data = _echo_payload(broken_graph_client.post(SNAPSHOT_URL, json=_payload()))
        assert data["current_node"] is None
        assert data["mastery"]["node_id"] is None
        assert data["mastery"]["level"] == "not_started"


class TestActivePlanAndEvidence:

    @pytest.mark.asyncio
    async def test_snap_empty_plan_yields_null_active_plan(self, client):
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload()))
        assert data["active_plan"] is None

    @pytest.mark.asyncio
    async def test_snap_current_step_is_lowest_order_open_step(self, client):
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(),
            steps=[
                _step(id=3, step_order=3, knowledge_node_id="cnn", status="pending"),
                _step(id=1, step_order=1, knowledge_node_id="ml_basics", status="completed"),
                _step(id=2, step_order=2, knowledge_node_id="dl_basics", status="pending"),
            ],
        )))
        current = data["active_plan"]["current_step"]
        assert current["step_id"] == 2
        assert current["node_id"] == "dl_basics"

    @pytest.mark.asyncio
    async def test_snap_all_steps_closed_yields_null_current_step(self, client):
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(),
            steps=[_step(id=1, status="completed"), _step(id=2, step_order=2, status="skipped")],
        )))
        assert data["active_plan"]["current_step"] is None

    @pytest.mark.asyncio
    async def test_snap_recent_evidence_is_capped_at_five_newest_first(self, client):
        """§2.4：固定 N=5，按 occurred_at 倒序。"""
        evidence = [
            _evidence(evidence_id=f"exercise:{1000+i}:ai_intro", node_id="__none__",
                      occurred_at=f"2026-09-{10+i:02d}T20:00:00+08:00", source_record_id=str(1000 + i))
            for i in range(8)
        ]
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(recent_evidence=evidence)))
        got = [ev["evidence_id"] for ev in data["recent_evidence"]]
        assert len(got) == 5
        assert got == [f"exercise:{1007-i}:ai_intro" for i in range(5)]

    @pytest.mark.asyncio
    async def test_snap_last_evidence_at_tracks_current_node_only(self, client):
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
            recent_evidence=[
                _evidence(occurred_at="2026-09-20T10:00:00+08:00"),
                _evidence(evidence_id="exercise:1002:ml_basics", occurred_at="2026-09-25T10:00:00+08:00"),
                _evidence(evidence_id="resource:r-9:cnn", node_id="cnn",
                          occurred_at="2026-09-27T10:00:00+08:00"),
            ],
        )))
        assert data["mastery"]["last_evidence_at"].startswith("2026-09-25T10:00:00")

    @pytest.mark.asyncio
    async def test_snap_profile_context_keeps_only_three_fields(self, client):
        """§2.5：只留 weak_points(≤3) / preferred_style / skill_level，禁止塞完整画像。"""
        data = _echo_payload(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
            student_profile={
                "weak_points": ["正则化", "梯度消失", "过拟合", "注意力机制"],
                "strong_points": ["线性代数"],
                "preferred_style": "visual",
                "email": "should-not-leak@example.com",
            },
        )))
        assert set(data["profile_context"]) == {"weak_points", "preferred_style", "skill_level"}
        assert len(data["profile_context"]["weak_points"]) <= 3
        assert data["profile_context"]["preferred_style"] == "visual"


# ═══════════════════════════════════════════════════════════════════
# Part 5 —— 对外形状与包契约（PKG-A02/A03/B04）
# ═══════════════════════════════════════════════════════════════════


class TestSnapshotSurfaceContract:

    @pytest.mark.asyncio
    async def test_snap_route_is_a_package_attribute(self):
        assert callable(getattr(internal_api, "get_learning_snapshot", None))

    @pytest.mark.asyncio
    async def test_snap_route_is_registered_in_router(self):
        table = set()
        for route in internal_api.router.routes:
            for method in (getattr(route, "methods", None) or set()):
                if method not in ("HEAD", "OPTIONS"):
                    table.add((method, route.path))
        assert ("POST", SNAPSHOT_URL) in table

    @pytest.mark.asyncio
    async def test_snap_submodule_uses_package_qualified_names(self):
        """PKG-B04：子模块必须写 `api.xxx`，裸名会让 monkeypatch 注入点静默失效。"""
        import ast
        from pathlib import Path

        src = Path(internal_api.__file__).resolve().parent / "snapshot.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        bare_allowed = {"sse_response", "safe_export_path", "api_success", "api_error", "_EXPORTS_DIR"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in bare_allowed:
                offenders.append((node.id, node.lineno))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.startswith("_get_"):
                    offenders.append((node.func.id, node.lineno))
        assert offenders == [], f"snapshot.py 存在裸名调用：{offenders}"

    @pytest.mark.asyncio
    async def test_snap_submodule_wraps_errors_and_delegates_once(self):
        """端点必须包错误信封，且装配点只取一次（避免二次构造/双重单例）。"""
        source = inspect.getsource(internal_api.get_learning_snapshot)
        assert "try" in source and "except" in source
        assert source.count("_get_graph_center()") == 1

    @pytest.mark.asyncio
    async def test_snap_read_model_does_no_io(self):
        """纯函数性质：`learning_snapshot` 模块不得引入任何 IO / DB / HTTP 依赖。"""
        import app.services.learning_snapshot as ls

        source = inspect.getsource(ls)
        for forbidden in ("import requests", "import httpx", "import sqlalchemy",
                          "psycopg", "open(", "session.add", "commit()"):
            assert forbidden not in source, f"读模型出现 IO 痕迹：{forbidden}"

    @pytest.mark.asyncio
    async def test_snap_invalid_body_is_422(self, client):
        resp = client.post(SNAPSHOT_URL, json={"student_id": 0, "course_id": ""})
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["success"] is False
        assert "student_id" in body["error"] or "course_id" in body["error"]
