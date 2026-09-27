"""P2 Task 2 契约测试：`LearningEvidence` 12 字段 + 幂等 + 非法组合拒绝。

对应验收项（P2 §7.3）：
- **A4**：同一证据两次 → 掌握度只变一次（幂等丢弃，不重复记账）。
- **A5**：非法 `(source_action, type)` 组合被拒（边界快速失败）。

同时冻结两件事：
1. `app/api/models.py` 的 12 字段模型与 `MasteryEvent` 的 `manual_correction` 扩展（P1 §4.2）；
2. 新路由 `/internal/evidence/apply` 的对外形状与错误信封。
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import internal_api
from app.services import evidence_contract as ec
from app.services import mastery_scale as ec_scale


EVIDENCE_URL = "/internal/evidence/apply"
MASTERIES_URL = "/internal/graph/masteries"


def _format_validation_error(exc: RequestValidationError) -> str:
    """与既有契约测试保持一致：`字段 '{field}' {msg}`。"""
    parts = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        field = ".".join(loc) or "(root)"
        parts.append(f"字段 '{field}' {err.get('msg', '')}")
    return "; ".join(parts)


@pytest.fixture()
def client() -> TestClient:
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

    ec.reset_seen()
    yield TestClient(app)
    ec.reset_seen()


def _evidence(**overrides) -> dict:
    base = {
        "evidence_id": "exercise:1001:ai_basics",
        "student_id": 7,
        "course_id": "ai_intro",
        "node_id": "ai_basics",
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


# ═══════════════════════════════════════════════════════════════════
# Part 1 —— 12 字段模型（P1 §4.1）
# ═══════════════════════════════════════════════════════════════════


class TestLearningEvidenceModel:

    @pytest.mark.asyncio
    async def test_evd_m01_twelve_fields_accepted(self, client):
        resp = client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_evd_m02_optional_fields_default_to_none(self, client):
        payload = _evidence()
        for optional in ("score_or_result", "confidence", "effect_hint"):
            payload.pop(optional)
        resp = client.post(EVIDENCE_URL, json={"evidence": payload, "current_mastery": 0.2})
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_evd_m03_missing_required_field_is_422(self, client):
        payload = _evidence()
        payload.pop("explanation")
        resp = client.post(EVIDENCE_URL, json={"evidence": payload, "current_mastery": 0.0})
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["success"] is False
        assert "explanation" in body["error"]

    @pytest.mark.asyncio
    async def test_evd_m04_empty_node_id_is_rejected(self, client):
        """node_id 不得为空串；无归属必须用保留值 __none__（P1 §4.1）。"""
        resp = client.post(
            EVIDENCE_URL, json={"evidence": _evidence(node_id=""), "current_mastery": 0.0},
        )
        assert resp.status_code == 422, resp.text
        assert "node_id" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_evd_m05_confidence_out_of_range_is_rejected(self, client):
        resp = client.post(
            EVIDENCE_URL, json={"evidence": _evidence(confidence=1.5), "current_mastery": 0.0},
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_evd_m06_mastery_event_literal_extended(self):
        """P1 §4.2：`MasteryEvent` 枚举扩展 `manual_correction`，其余 4 值不动。"""
        from app.api.models import MasteryEvent

        allowed = MasteryEvent.model_fields["event_type"].annotation
        assert ec.TYPE_MANUAL_CORRECTION in str(allowed)
        for value in ec.EVIDENCE_TYPES:
            assert value in str(allowed)

    @pytest.mark.asyncio
    async def test_evd_m07_response_shape_has_idempotency_key(self, client):
        resp = client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        data = resp.json()["data"]
        assert data["applied"] is True
        assert data["effect"] == "mastery_updated"
        assert data["idempotent_key"] == ec.idempotent_key(
            student_id=7, course_id="ai_intro", node_id="ai_basics",
            source_action="exercise", source_record_id="1001",
        )
        assert data["mastery_level"] in ec_scale.MASTERY_LEVELS
        assert data["mastery_level"] == ec_scale.mastery_to_level(data["new_mastery"])
        assert data["explanation"]


# ═══════════════════════════════════════════════════════════════════
# Part 2 —— A4：幂等（同一证据两次 → 只记账一次）
# ═══════════════════════════════════════════════════════════════════


class TestEvidenceIdempotency:

    @pytest.mark.asyncio
    async def test_evd_a4_same_evidence_twice_applies_once(self, client):
        first = client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        assert first.status_code == 200, first.text
        first_data = first.json()["data"]
        assert first_data["applied"] is True
        assert first_data["new_mastery"] == 0.4  # exercise_done score=1.0: 0 + (1-0)*0.4

        second = client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        assert second.status_code == 200, second.text
        second_data = second.json()["data"]
        assert second_data["applied"] is False
        assert second_data["effect"] == "duplicate_discarded"
        assert second_data["new_mastery"] is None
        assert "幂等" in second_data["explanation"]

    @pytest.mark.asyncio
    async def test_evd_a4_graph_endpoint_agrees_on_single_application(self, client):
        """跨端点一致性：同一条证据在证据域只记一次，用图谱域重放算出的值应与其一致。"""
        applied = client.post(
            EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0},
        ).json()["data"]
        client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})

        graph = client.post(MASTERIES_URL, json={
            "course_id": "ai_intro",
            "masteries": {},
            "events": [{"node_id": "ai_basics", "event_type": "exercise_done", "score": 1.0}],
        })
        assert graph.status_code == 200, graph.text
        assert graph.json()["data"]["masteries"]["ai_basics"] == applied["new_mastery"] == 0.4

    @pytest.mark.asyncio
    async def test_evd_a4_different_node_is_not_a_duplicate(self, client):
        client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        other = client.post(
            EVIDENCE_URL,
            json={"evidence": _evidence(node_id="ai_search", evidence_id="exercise:1001:ai_search"),
                  "current_mastery": 0.0},
        )
        assert other.json()["data"]["applied"] is True

    @pytest.mark.asyncio
    async def test_evd_a4_different_source_record_is_not_a_duplicate(self, client):
        client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        other = client.post(
            EVIDENCE_URL,
            json={"evidence": _evidence(source_record_id="1002", evidence_id="exercise:1002:ai_basics"),
                  "current_mastery": 0.0},
        )
        assert other.json()["data"]["applied"] is True

    @pytest.mark.asyncio
    async def test_evd_a4_retry_returns_200_not_error(self, client):
        """P1 §4.4 规则 1：重复提交不报错，幂等返回首次结果形状。"""
        client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        retry = client.post(EVIDENCE_URL, json={"evidence": _evidence(), "current_mastery": 0.0})
        assert retry.status_code == 200
        assert retry.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════
# Part 3 —— A5：非法组合拒绝（P1 §4.3 映射矩阵）
# ═══════════════════════════════════════════════════════════════════


LEGAL_MATRIX = {
    "exercise": ("exercise_done", "exercise_failed"),
    "plan": ("exercise_done", "exercise_failed", "resource_viewed"),
    "resource": ("resource_viewed",),
    "tutor": ("tutor_question_asked",),
    "manual": ("manual_correction",),
}

ILLEGAL_MATRIX = {
    "exercise": ("resource_viewed", "tutor_question_asked", "manual_correction"),
    "plan": ("tutor_question_asked", "manual_correction"),
    "resource": ("exercise_done", "exercise_failed", "tutor_question_asked", "manual_correction"),
    "tutor": ("resource_viewed", "exercise_done", "manual_correction"),
    "manual": ("resource_viewed", "exercise_done", "tutor_question_asked"),
}


class TestSourceActionMatrix:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source_action", sorted(LEGAL_MATRIX))
    async def test_evd_a5_legal_combinations_accepted(self, client, source_action):
        for evidence_type in LEGAL_MATRIX[source_action]:
            payload = _evidence(
                source_action=source_action,
                type=evidence_type,
                source_record_id=f"ok-{source_action}-{evidence_type}",
                evidence_id=f"{source_action}:ok:{evidence_type}",
                score_or_result=0.5,
            )
            resp = client.post(EVIDENCE_URL, json={"evidence": payload, "current_mastery": 0.2})
            assert resp.status_code == 200, f"{source_action}/{evidence_type} 应被接受：{resp.text}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source_action", sorted(ILLEGAL_MATRIX))
    async def test_evd_a5_illegal_combinations_rejected(self, client, source_action):
        for evidence_type in ILLEGAL_MATRIX[source_action]:
            payload = _evidence(
                source_action=source_action,
                type=evidence_type,
                source_record_id=f"bad-{source_action}-{evidence_type}",
                evidence_id=f"{source_action}:bad:{evidence_type}",
                score_or_result=0.5,
            )
            resp = client.post(EVIDENCE_URL, json={"evidence": payload, "current_mastery": 0.2})
            assert resp.status_code == 400, f"{source_action}/{evidence_type} 应被拒：{resp.text}"
            body = resp.json()
            assert body["success"] is False
            assert body["errorCode"] == "INVALID_REQUEST"

    @pytest.mark.asyncio
    async def test_evd_a5_unknown_source_action_is_422(self, client):
        """未知 source_action 被 Pydantic Literal 挡在模型层。"""
        resp = client.post(
            EVIDENCE_URL,
            json={"evidence": _evidence(source_action="telepathy"), "current_mastery": 0.0},
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_evd_a5_unknown_type_is_422(self, client):
        resp = client.post(
            EVIDENCE_URL,
            json={"evidence": _evidence(type="vibes"), "current_mastery": 0.0},
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_evd_a5_rejection_does_not_consume_idempotency_key(self, client):
        """非法请求不应污染去重表：改正后重提必须被接受。"""
        bad = _evidence(source_action="resource", type="exercise_done")
        client.post(EVIDENCE_URL, json={"evidence": bad, "current_mastery": 0.2})
        good = _evidence(source_action="resource", type="resource_viewed")
        resp = client.post(EVIDENCE_URL, json={"evidence": good, "current_mastery": 0.2})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["applied"] is True

    @pytest.mark.asyncio
    async def test_evd_a5_matrix_matches_frozen_contract(self):
        """矩阵本身是冻结契约，任何改动都必须同步改测试（防静默漂移）。"""
        assert ec.SOURCE_ACTION_TO_TYPES == LEGAL_MATRIX
        assert set(ec.SOURCE_ACTIONS) == set(LEGAL_MATRIX)

    @pytest.mark.asyncio
    async def test_evd_rejected_manual_correction_does_not_poison_key(self, client):
        """非数值人工纠正被拒后，改正重提必须被接受（幂等表不得被计算期异常污染）。

        回归：曾出现 `mark_seen` 早于 `compute_new_mastery`，被拒请求仍占键，
        导致改正后的合法纠正被误判重复而静默丢弃。
        """
        bad = _evidence(type="manual_correction", source_action="manual",
                        score_or_result="很努力", source_record_id="m-poison",
                        evidence_id="manual:m-poison:ai_basics")
        rejected = client.post(EVIDENCE_URL, json={"evidence": bad, "current_mastery": 0.2})
        assert rejected.status_code == 400, rejected.text

        good = _evidence(type="manual_correction", source_action="manual",
                         score_or_result=0.85, source_record_id="m-poison",
                         evidence_id="manual:m-poison:ai_basics")
        retried = client.post(EVIDENCE_URL, json={"evidence": good, "current_mastery": 0.2})
        assert retried.status_code == 200, retried.text
        data = retried.json()["data"]
        assert data["applied"] is True
        assert data["effect"] == "mastery_updated"
        assert data["new_mastery"] == 0.85


# ═══════════════════════════════════════════════════════════════════
# Part 4 —— 算法口径（与图谱域同一 PlanService.update_mastery）
# ═══════════════════════════════════════════════════════════════════


class TestEvidenceMasteryMath:

    @pytest.mark.asyncio
    async def test_evd_algo_matches_graph_center_math(self):
        """证据域与图谱域必须算出同一个数（口径唯一，P1 §3.3）。"""
        from app.services.plan_service import PlanService

        for etype, score in [("exercise_done", 0.8), ("exercise_failed", None),
                             ("resource_viewed", None), ("tutor_question_asked", None)]:
            assert ec.compute_new_mastery(0.5, etype, score) == PlanService.update_mastery(0.5, etype, score)

    @pytest.mark.asyncio
    async def test_evd_manual_correction_overrides(self):
        """人工纠正 = 覆盖（强证据，confidence=1.0），不是累积。"""
        assert ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, 0.9) == 0.9
        assert ec.compute_new_mastery(0.9, ec.TYPE_MANUAL_CORRECTION, 0.1) == 0.1

    @pytest.mark.asyncio
    async def test_evd_manual_correction_without_value_keeps_current(self):
        assert ec.compute_new_mastery(0.37, ec.TYPE_MANUAL_CORRECTION, None) == 0.37

    @pytest.mark.asyncio
    async def test_evd_manual_correction_rejects_non_numeric(self):
        with pytest.raises(ec.EvidenceContractError):
            ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, "很努力")

    @pytest.mark.asyncio
    async def test_evd_manual_correction_rejects_bool(self):
        """bool 是 int 子类，不得被静默当成 1.0/0.0（权威掌握度必须显式数值）。"""
        with pytest.raises(ec.EvidenceContractError):
            ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, True)
        with pytest.raises(ec.EvidenceContractError):
            ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, False)

    @pytest.mark.asyncio
    async def test_evd_manual_correction_clamps_to_unit_range(self):
        assert ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, 1.4) == 1.0
        assert ec.compute_new_mastery(0.2, ec.TYPE_MANUAL_CORRECTION, -0.3) == 0.0

    @pytest.mark.asyncio
    async def test_evd_none_node_records_without_mastery(self, client):
        """无归属证据只记事实（P1 §4.1 保留值 __none__）。"""
        resp = client.post(EVIDENCE_URL, json={
            "evidence": _evidence(node_id="__none__", type="tutor_question_asked",
                                  source_action="tutor", source_record_id="t-1",
                                  evidence_id="tutor:t-1:__none__", score_or_result=None),
            "current_mastery": 0.0,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["applied"] is True
        assert data["effect"] == "recorded_without_mastery"
        assert data["new_mastery"] is None
        assert data["mastery_level"] == "not_started"

    @pytest.mark.asyncio
    async def test_evd_weak_evidence_is_flagged(self, client):
        weak = client.post(EVIDENCE_URL, json={
            "evidence": _evidence(type="resource_viewed", source_action="resource",
                                  source_record_id="r-1", evidence_id="resource:r-1:ai_basics"),
            "current_mastery": 0.2,
        }).json()["data"]
        assert weak["weak_evidence"] is True

        strong = client.post(EVIDENCE_URL, json={
            "evidence": _evidence(), "current_mastery": 0.2,
        }).json()["data"]
        assert strong["weak_evidence"] is False


# ═══════════════════════════════════════════════════════════════════
# Part 5 —— 包契约与新路由（PKG-A02 / A03 / B04）
# ═══════════════════════════════════════════════════════════════════


class TestEvidenceSurfaceContract:

    @pytest.mark.asyncio
    async def test_evd_route_is_a_package_attribute(self):
        assert callable(getattr(internal_api, "apply_learning_evidence", None))

    @pytest.mark.asyncio
    async def test_evd_route_is_registered_in_router(self):
        table = set()
        for route in internal_api.router.routes:
            for method in (getattr(route, "methods", None) or set()):
                if method not in ("HEAD", "OPTIONS"):
                    table.add((method, route.path))
        assert ("POST", EVIDENCE_URL) in table

    @pytest.mark.asyncio
    async def test_evd_submodule_uses_package_qualified_names(self):
        """PKG-B04：子模块必须写 `api.xxx`，裸名会让 monkeypatch 注入点静默失效。"""
        import ast
        from pathlib import Path

        src = Path(internal_api.__file__).resolve().parent / "evidence.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        bare_allowed = {"sse_response", "safe_export_path", "api_success", "api_error", "_EXPORTS_DIR"}
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in bare_allowed:
                offenders.append((node.id, node.lineno))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.startswith("_get_"):
                    offenders.append((node.func.id, node.lineno))
        assert offenders == [], f"evidence.py 存在裸名调用：{offenders}"

    @pytest.mark.asyncio
    async def test_evd_submodule_wraps_errors(self):
        """证据端点必须包错误信封（与 /graph/masteries 的唯一例外不同）。"""
        import inspect

        source = inspect.getsource(internal_api.apply_learning_evidence)
        assert "try" in source and "except" in source
