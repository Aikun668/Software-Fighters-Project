"""P2 Task 1 契约测试 — 口径统一（五级 level 映射 + 阈值 + 缺失数据默认值）。

对应 P1 §6.3：
- A1：`level` 映射在 0.3 / 0.6 / 0.85 边界一致
- A3：无记录 → 默认值 0.0（非 0.5）

本文件是**契约测试**（离线，非 harness）。逐方法标注 @pytest.mark.asyncio
（项目约定：ai-service 异步测试须逐方法标注，否则 RED 证据无效）。
"""

import pytest


class TestMasteryToLevelBoundaries:
    """A1：五级 level 映射边界（P1 §3.4 冻结表）。

    期望 `app.services.mastery_scale` 提供 `mastery_to_level` 与五个 LEVEL_* 常量。
    RED 阶段该模块尚不存在 → 本类全部报 ImportError。
    """

    def test_no_record_is_not_started(self):
        """null（无记录）→ not_started。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(None) == "not_started"

    def test_zero_is_not_started(self):
        """0.0 → not_started（与 null 在 level 上合并）。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.0) == "not_started"

    def test_just_above_zero_is_beginner(self):
        """(0, 0.3) 开区间左端 → beginner。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.01) == "beginner"

    def test_just_below_point3_is_beginner(self):
        """(0, 0.3) 开区间右端 0.29 → beginner。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.29) == "beginner"

    def test_point3_boundary_is_learning(self):
        """0.3 是 [0.3, 0.6) 的左闭边界 → learning。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.3) == "learning"

    def test_just_below_point6_is_learning(self):
        """[0.3, 0.6) 右端 0.59 → learning。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.59) == "learning"

    def test_point6_boundary_is_proficient(self):
        """0.6 是 [0.6, 0.85) 的左闭边界 → proficient。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.6) == "proficient"

    def test_just_below_point85_is_proficient(self):
        """[0.6, 0.85) 右端 0.84 → proficient。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.84) == "proficient"

    def test_point85_boundary_is_mastered(self):
        """0.85 是 [0.85, 1.0] 的左闭边界 → mastered。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(0.85) == "mastered"

    def test_one_is_mastered(self):
        """上界 1.0 → mastered。"""
        from app.services.mastery_scale import mastery_to_level
        assert mastery_to_level(1.0) == "mastered"


class TestExerciseProfileThresholdAlignment:
    """缺口③：exercise_profile_service 阈值 80→85（百分制），60 不动。

    P1 §3.4 澄清：此处阈值是**准确率百分数**，不是掌握度小数。
    """

    def test_accuracy_85_is_proficient(self):
        from app.services.exercise_profile_service import enrich_profile

        result = enrich_profile(
            1,
            session_analysis={"per_node": [
                {"knowledge_node_id": "n1", "accuracy": 85, "total": 10},
            ]},
        )
        assert result["updated_profile"]["skill_levels"]["n1"]["level"] == "proficient"

    def test_accuracy_80_is_no_longer_proficient(self):
        """80 是旧阈值边界 —— 改后应降为 developing（RED 断言）。"""
        from app.services.exercise_profile_service import enrich_profile

        result = enrich_profile(
            1,
            session_analysis={"per_node": [
                {"knowledge_node_id": "n1", "accuracy": 80, "total": 10},
            ]},
        )
        assert result["updated_profile"]["skill_levels"]["n1"]["level"] == "developing"

    def test_accuracy_60_is_still_developing(self):
        """60 是 proficient 下界 0.6 的另一套口径，不改。"""
        from app.services.exercise_profile_service import enrich_profile

        result = enrich_profile(
            1,
            session_analysis={"per_node": [
                {"knowledge_node_id": "n1", "accuracy": 60, "total": 5},
            ]},
        )
        assert result["updated_profile"]["skill_levels"]["n1"]["level"] == "developing"


class TestMissingDataDefaultsToZero:
    """A3：无记录 → 0.0（非 0.5）。P1 §3.5 冻结。"""

    def test_old_mastery_no_node_id_returns_zero(self):
        """plan_center._old_mastery：无 knowledge_node_id → 0.0。"""
        from app.centers.plan_center import PlanCenter

        got = PlanCenter._old_mastery({}, "")
        assert got == 0.0

    def test_old_mastery_missing_key_returns_zero(self):
        """plan_center._old_mastery：masteries 无该 key → 0.0（不是 0.5）。"""
        from app.centers.plan_center import PlanCenter

        got = PlanCenter._old_mastery({}, "n1")
        assert got == 0.0

    def test_old_mastery_reads_primary_source(self):
        """有记录时取 masteries 的值（唯一真源）。"""
        from app.centers.plan_center import PlanCenter

        assert PlanCenter._old_mastery({"n1": 0.62}, "n1") == 0.62

    def test_old_mastery_signature_rejects_step_snapshot(self):
        """契约：签名不再接受 step —— 快照无法作为计算输入（P1 §3.3）。"""
        import inspect

        from app.centers.plan_center import PlanCenter

        params = list(inspect.signature(PlanCenter._old_mastery).parameters)
        assert params == ["masteries", "knowledge_node_id"]

    @pytest.mark.asyncio
    async def test_apply_node_status_change_missing_mastery_uses_zero(self):
        """plan_service.apply_node_status_change：masteries 缺失 → mastery_current 取 0.0。"""
        from app.services.plan_service import PlanService

        steps = [{"step_order": 1, "topic": "变量", "knowledge_node_id": "n1", "status": "pending"}]
        result = PlanService.apply_node_status_change(
            steps=steps, node_id="n1", new_status="learning", old_status="locked",
            masteries={}, plan_status="active",
        )
        updated = result["updated_steps"][0]
        assert updated["mastery_current"] == 0.0
