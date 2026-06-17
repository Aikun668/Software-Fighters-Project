"""Tests for exercise profile enrichment service — pure computation."""

from app.services.exercise_profile_service import enrich_profile


class TestEnrichProfile:
    def test_empty_profile(self):
        result = enrich_profile(1)
        updated = result["updated_profile"]
        assert updated["weak_points"] == []
        assert updated["strong_points"] == []
        assert updated["skill_levels"] == {}
        assert updated["suggested_focus"] == []

    def test_merges_weak_points(self):
        result = enrich_profile(
            1,
            student_profile={"weak_points": ["ml_basics"]},
            session_analysis={
                "weak_nodes": [{"knowledge_node_id": "backprop", "current_mastery": 0.2}],
                "strengths": [],
            },
        )
        updated = result["updated_profile"]
        assert "ml_basics" in updated["weak_points"]
        assert "backprop" in updated["weak_points"]

    def test_removes_weak_when_becomes_strong(self):
        result = enrich_profile(
            1,
            student_profile={"weak_points": ["backprop"]},
            session_analysis={
                "weak_nodes": [],
                "strengths": [{"knowledge_node_id": "backprop"}],
            },
        )
        updated = result["updated_profile"]
        assert "backprop" not in updated["weak_points"]
        assert "backprop" in updated["strong_points"]

    def test_strong_removed_when_becomes_weak(self):
        result = enrich_profile(
            1,
            student_profile={"strong_points": ["backprop"]},
            session_analysis={
                "weak_nodes": [{"knowledge_node_id": "backprop", "current_mastery": 0.2}],
                "strengths": [],
            },
        )
        updated = result["updated_profile"]
        assert "backprop" not in updated["strong_points"]
        assert "backprop" in updated["weak_points"]

    def test_skill_levels_from_per_node(self):
        result = enrich_profile(
            1,
            session_analysis={
                "per_node": [
                    {"knowledge_node_id": "n1", "accuracy": 90, "total": 10},
                    {"knowledge_node_id": "n2", "accuracy": 60, "total": 5},
                    {"knowledge_node_id": "n3", "accuracy": 30, "total": 3},
                ],
            },
        )
        levels = result["updated_profile"]["skill_levels"]
        assert levels["n1"]["level"] == "proficient"
        assert levels["n2"]["level"] == "developing"
        assert levels["n3"]["level"] == "beginner"

    def test_suggested_focus_high_priority(self):
        result = enrich_profile(
            1,
            session_analysis={
                "weak_nodes": [
                    {"knowledge_node_id": "gap", "current_mastery": 0.1},
                    {"knowledge_node_id": "gap2", "current_mastery": 0.3},
                ],
                "strengths": [],
                "mastery_updates": [],
            },
        )
        focus = result["updated_profile"]["suggested_focus"]
        assert len(focus) > 0
        assert focus[0]["priority"] == "high"
        assert focus[0]["knowledge_node_id"] == "gap"  # lower mastery first

    def test_suggested_focus_improving(self):
        result = enrich_profile(
            1,
            session_analysis={
                "weak_nodes": [],
                "strengths": [],
                "mastery_updates": [
                    {"knowledge_node_id": "rising", "old_mastery": 0.2, "new_mastery": 0.5},
                ],
            },
        )
        focus = result["updated_profile"]["suggested_focus"]
        assert any(f["knowledge_node_id"] == "rising" for f in focus)

    def test_no_duplicate_weak_points(self):
        result = enrich_profile(
            1,
            student_profile={"weak_points": [{"knowledge_node_id": "n1"}]},
            session_analysis={
                "weak_nodes": [{"knowledge_node_id": "n1", "current_mastery": 0.1}],
                "strengths": [],
            },
        )
        updated = result["updated_profile"]
        assert updated["weak_points"].count("n1") <= 1

    def test_handles_weak_points_as_strings(self):
        result = enrich_profile(
            1,
            student_profile={"weak_points": ["existing_node"]},
            session_analysis={
                "weak_nodes": [{"knowledge_node_id": "new_node", "current_mastery": 0.2}],
                "strengths": [],
            },
        )
        updated = result["updated_profile"]
        assert "existing_node" in updated["weak_points"]
        assert "new_node" in updated["weak_points"]

    def test_max_five_suggested_focus(self):
        result = enrich_profile(
            1,
            session_analysis={
                "weak_nodes": [
                    {"knowledge_node_id": f"w{i}", "current_mastery": 0.1 * i}
                    for i in range(1, 8)
                ],
                "strengths": [],
                "mastery_updates": [],
            },
        )
        assert len(result["updated_profile"]["suggested_focus"]) <= 5
