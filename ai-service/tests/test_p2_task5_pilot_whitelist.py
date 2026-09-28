"""P2 Task 5 契约测试：试点课程白名单（总纲 §5.5 第 1 条）。

对应 RED 断言（P2 §六 Task 表行 5）：
**「白名单外课程不返回 `next_action`」**。

## 本 Task 的裁决（先斩后奏，登记于此）

P2 方案表内有两处看似冲突的表述，本模块确认它们**并不冲突**，各说一半：

1. `§〇 问题 2` 变更表末行：`| 试点开关 | 无 | 课程白名单/功能开关（总纲 §5.5 第 1 条） | Java（配置） |`
   —— 说的是**开关的配置真源在 Java**（谁能开、开哪些课，属部署配置）。
2. `§六 Task 表` 行 5：`| 5 | 试点白名单 | Python | 仅 ai_intro 生效… |`
   —— 说的是**开关的执行点在 Python**（读模型确实要为白名单外课程降级）。

两者合并才是完整职责：**Java 持有配置，Python 执行闸门**（与「Java 是真源 + 唯一写入者、
Python 零状态只计算」的边界规则 1 一致 —— Python 不得读 DB，也就无法自己决定谁能试点，
只能执行传进来的 `course_id` 判定）。

**Task 4 的「白名单校验」不是本 Task 的重名项**：P1 方案 `:401` 写的是
`next_action 从不返回跨域指令（白名单校验）`，指的是 **`entry` 必须落在既有业务域路由
白名单内**（已由 `next_action.ENTRY_BY_KIND` 实现）。本 Task 的「试点白名单」是**课程级**
的放量闸门，二者层次不同。

## 闸门语义（V1 冻结）

- 白名单 = `{"ai_intro"}`（总纲 §5.5 第 1 条；P2 §2.5 确认试点课程）；
- **精确匹配、区分大小写**（不做归一化 —— 归一化会悄悄放大试点范围，与「限制试点」相反）；
- 非白名单课程 → `next_action = null`，**其余 9 个键与 Task 3 完全一致**：这就是 Task 表
  要求的「降级为旧行为」——`next_action: null` 正是 Task 4 落地前的形状；
- 闸门**只作用于建议**，不影响 `current_node` / `mastery` / `freshness` 的计算，
  也不产生任何新增 IO（判定是纯集合成员测试）。
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import internal_api
from app.centers.graph_center import GraphCenter
from app.services import learning_snapshot
from app.services import pilot_scope
from app.services.graph_service import GraphService


SNAPSHOT_URL = "/internal/snapshot"

# P1 §二 冻结的 10 键（与 Task 3 的契约测试同集合；此处再冻一次，
# 用来证明「白名单外降级」只是把 next_action 置空，而不是少给或多给键）。
SNAPSHOT_KEYS = frozenset({
    "student_id", "course_id", "generated_at", "active_plan", "current_node",
    "mastery", "recent_evidence", "profile_context", "freshness", "next_action",
})

NON_PILOT_COURSE = "data_structure"

# 冻结时钟：`generated_at` 会进「逐键相等」对比，若用真实 `now` 则两次调用微秒级
# 必不同，断言退化为**看时钟精度**（Windows 上曾经因此侥幸通过）。显式注入，
# 让对比只测闸门、不测时钟。
FROZEN_NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


def _format_validation_error(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        field = ".".join(loc) or "(root)"
        parts.append(f"字段 '{field}' {err.get('msg', '')}")
    return "; ".join(parts)


class _RecordingCenter:
    def __init__(self, real, calls: list[tuple[str, dict]]):
        self._real = real
        self._calls = calls

    async def get_graph(self, **kwargs):
        self._calls.append(("get_graph", kwargs))
        return await self._real.get_graph(**kwargs)

    async def recommend_next_node(self, **kwargs):
        self._calls.append(("recommend_next_node", kwargs))
        return await self._real.recommend_next_node(**kwargs)


@pytest.fixture()
def graph_calls() -> list[tuple[str, dict]]:
    return []


@pytest.fixture()
def client(graph_calls, monkeypatch) -> TestClient:
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
    active_at = (FROZEN_NOW - timedelta(hours=6)).isoformat()
    base = {"id": 42, "title": "AI 入门 30 天", "status": "in_progress",
            "last_activity_at": active_at}
    base.update(overrides)
    return base


def _step(**overrides) -> dict:
    base = {
        "id": 1, "step_order": 1, "topic": "机器学习基础",
        "knowledge_node_id": "ml_basics", "status": "in_progress",
        "mastery_current": None, "mastery_after": None,
    }
    base.update(overrides)
    return base


def _data(resp) -> dict:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


def _would_fire_review(**overrides) -> dict:
    """一组**必定命中 §5.3 行 2** 的读模型入参（当前步骤节点 + `learning` 档）。

    之所以要「必定命中」：闸门测试必须排除「规则本来就没命中」这一混淆解释 ——
    只有当同一组入参在白名单内**确实产出建议**、在白名单外**被置空**时，
    `None` 才能归因于闸门本身。
    """
    kwargs = dict(
        student_id=7,
        plan=_plan(),
        steps=[_step()],
        masteries={"ml_basics": 0.4},
        recent_evidence=[],
        student_profile={},
        recent_records=[],
        session_analysis={},
        graph_nodes=[{"id": "ml_basics", "name": "机器学习基础"}],
        now=FROZEN_NOW,
    )
    kwargs.update(overrides)
    return kwargs


# ═══════════════════════════════════════════════════════════════════
# Part 1 —— 白名单常量的形状与判定
# ═══════════════════════════════════════════════════════════════════


class TestPilotScope:
    def test_pilot_course_ids_is_frozen(self):
        """白名单是**冻结集合**，V1 只含试点课程 `ai_intro`（P2 §2.5）。"""
        assert isinstance(pilot_scope.PILOT_COURSE_IDS, frozenset)
        assert pilot_scope.PILOT_COURSE_IDS == frozenset({"ai_intro"})

    def test_is_pilot_course_accepts_ai_intro(self):
        assert pilot_scope.is_pilot_course("ai_intro") is True

    def test_is_pilot_course_rejects_other_course(self):
        assert pilot_scope.is_pilot_course(NON_PILOT_COURSE) is False

    @pytest.mark.parametrize("value", ["AI_INTRO", "Ai_Intro", " ai_intro", "ai_intro "])
    def test_is_pilot_course_is_exact_match_case_sensitive(self, value):
        """不做大小写/空白归一化：归一化会**放大**试点范围，与「限制试点」的目的相反。"""
        assert pilot_scope.is_pilot_course(value) is False

    @pytest.mark.parametrize("value", [None, "", 0, [], {}])
    def test_is_pilot_course_is_total_over_non_strings(self, value):
        """判定必须对任意输入返回布尔（路由层是系统边界，不得靠调用方先验类型）。"""
        assert pilot_scope.is_pilot_course(value) is False


# ═══════════════════════════════════════════════════════════════════
# Part 2 —— 读模型层闸门（决定性证据：同一入参，只换 course_id）
# ═══════════════════════════════════════════════════════════════════


class TestSnapshotGate:
    def test_pilot_course_yields_suggestion(self):
        """基线：白名单内课程 → 建议照常产出（`review_current_node`）。"""
        snap = learning_snapshot.build_snapshot(
            course_id="ai_intro", **_would_fire_review(),
        )
        assert snap["next_action"] is not None
        assert snap["next_action"]["action_kind"] == "review_current_node"

    def test_non_pilot_course_suppresses_suggestion(self):
        """**核心 RED 断言**：白名单外课程 → `next_action is None`。"""
        snap = learning_snapshot.build_snapshot(
            course_id=NON_PILOT_COURSE, **_would_fire_review(),
        )
        assert snap["next_action"] is None

    def test_non_pilot_course_degrades_only_the_suggestion(self):
        """「降级为旧行为」= 只置空建议；`current_node` / `mastery` 等照常计算。"""
        snap = learning_snapshot.build_snapshot(
            course_id=NON_PILOT_COURSE, **_would_fire_review(),
        )
        assert snap["current_node"]["node_id"] == "ml_basics"
        assert snap["current_node"]["reason"] == "current_step_node"
        assert snap["mastery"]["level"] == "learning"
        assert snap["mastery"]["source"] == "node_masteries"
        assert snap["course_id"] == NON_PILOT_COURSE
        assert set(snap.keys()) == SNAPSHOT_KEYS

    def test_gate_is_the_only_difference_between_the_two(self):
        """逐一对比：除 `course_id` 与 `next_action` 外，两个快照**逐键相等**。

        这是闸门归因的最强证明 —— 排除了图谱缺失、规则未命中等一切替代解释。
        `now` 已冻结（`FROZEN_NOW`），故 `generated_at` 的相等不是靠时钟精度，
        而是真的没被闸门碰到。
        """
        plain = learning_snapshot.build_snapshot(
            course_id="ai_intro", **_would_fire_review(),
        )
        gated = learning_snapshot.build_snapshot(
            course_id=NON_PILOT_COURSE, **_would_fire_review(),
        )
        for key in SNAPSHOT_KEYS - {"course_id", "next_action"}:
            assert gated[key] == plain[key], f"键 {key} 不应受试点闸门影响"
        assert plain["next_action"] is not None
        assert gated["next_action"] is None

    def test_gate_does_not_require_graph(self):
        """闸门是纯集合判定：无图谱时同样生效（且不抛异常）。"""
        snap = learning_snapshot.build_snapshot(
            course_id=NON_PILOT_COURSE,
            **_would_fire_review(graph_nodes=[]),
        )
        assert snap["next_action"] is None

    def test_pure_rule_engine_has_no_course_concept(self):
        """`build_next_action` 保持**无课程上下文**：闸门在读模型层，不在规则引擎里。

        若把 course 塞进纯函数，规则引擎就被耦合到「试点范围」这一部署策略上；
        冻结当前签名，防止后续把策略下沉进规则。
        """
        import inspect

        params = inspect.signature(learning_snapshot.build_next_action).parameters
        assert "course_id" not in params
        assert "course" not in " ".join(params)


# ═══════════════════════════════════════════════════════════════════
# Part 3 —— 端点层：白名单外课程不报错，只是没有建议
# ═══════════════════════════════════════════════════════════════════


class TestSnapshotEndpointScope:
    def test_endpoint_pilot_course_returns_suggestion(self, client):
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert data["next_action"] is not None
        assert data["next_action"]["action_kind"] == "review_current_node"

    def test_endpoint_non_pilot_course_degrades_not_errors(self, client):
        """**端点级 RED 断言**：白名单外课程 → 200 + `next_action: null`（不是报错）。

        本用例的载荷带了 `steps=[_step()]`（绑定 `ml_basics`）与
        `masteries={"ml_basics": 0.4}`，故 `current_node` 走 `current_step_node`
        分支、`mastery.level == learning` —— **与图谱无关**，即使课程未知也不缺。
        也就是说：去掉闸门时这里本会返回 `review_current_node`，`None` 是**单因**
        归因于闸门，而非「未知课程取不到节点」。闸门的最强证据仍是 Part 2 的
        `test_gate_is_the_only_difference_between_the_two`（同入参只换 `course_id`，
        逐键对比）；本用例冻结的是**对外行为**：降级而非 5xx。
        """
        data = _data(client.post(SNAPSHOT_URL, json=_payload(
            course_id=NON_PILOT_COURSE,
            plan=_plan(), steps=[_step()], masteries={"ml_basics": 0.4},
        )))
        assert set(data.keys()) == SNAPSHOT_KEYS
        assert data["course_id"] == NON_PILOT_COURSE
        assert data["next_action"] is None
        # 闸门只置空建议：节点与掌握度照常算出，证明降级不是「整份快照塌掉」。
        assert data["current_node"]["node_id"] == "ml_basics"
        assert data["mastery"]["level"] == "learning"

    def test_endpoint_empty_course_id_still_rejected(self, client):
        """空白 `course_id` 仍由请求模型拒绝（`min_length=1`）—— 闸门不放宽入参校验。"""
        resp = client.post(SNAPSHOT_URL, json=_payload(course_id=""))
        assert resp.status_code == 422
