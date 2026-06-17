"""Tests for exercise analytics service — pure computation, no mocking needed."""

from app.services.exercise_analytics_service import analyze_session, get_dashboard


class TestAnalyzeSession:
    def test_empty_records(self):
        result = analyze_session([], {})
        assert result["total_questions"] == 0
        assert result["accuracy_pct"] == 0
        assert result["per_node"] == []
        assert result["mastery_updates"] == []

    def test_all_correct(self):
        records = [
            {"knowledge_node_id": "backprop", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 30, "difficulty": 3},
        ]
        result = analyze_session(records, masteries={"backprop": 0.5})
        assert result["total_questions"] == 1
        assert result["correct_count"] == 1
        assert result["accuracy_pct"] == 100
        assert result["overall_score"] == 100
        assert len(result["strengths"]) >= 1

    def test_all_wrong(self):
        records = [
            {"knowledge_node_id": "backprop", "question": "q1",
             "question_type": "choice", "user_answer": "X", "correct_answer": "A",
             "is_correct": False, "time_spent_seconds": 30, "difficulty": 3},
        ]
        result = analyze_session(records, masteries={"backprop": 0.5})
        assert result["accuracy_pct"] == 0
        assert len(result["weak_nodes"]) >= 1
        assert len(result["suggestions"]) >= 1

    def test_mixed_results(self):
        records = [
            {"knowledge_node_id": "n1", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
            {"knowledge_node_id": "n1", "question": "q2",
             "question_type": "choice", "user_answer": "B", "correct_answer": "C",
             "is_correct": False, "time_spent_seconds": 20, "difficulty": 3},
            {"knowledge_node_id": "n2", "question": "q3",
             "question_type": "short_answer", "user_answer": "x", "correct_answer": "x",
             "is_correct": True, "time_spent_seconds": 15, "difficulty": 4},
        ]
        result = analyze_session(records, {})
        assert result["total_questions"] == 3
        assert result["correct_count"] == 2
        assert result["accuracy_pct"] == 67

    def test_mastery_increases_on_correct(self):
        records = [
            {"knowledge_node_id": "node_a", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 30, "difficulty": 3},
        ]
        result = analyze_session(records, masteries={"node_a": 0.3})
        assert len(result["mastery_updates"]) >= 1
        update = result["mastery_updates"][0]
        assert update["knowledge_node_id"] == "node_a"
        assert update["new_mastery"] > update["old_mastery"]

    def test_mastery_decreases_on_wrong(self):
        records = [
            {"knowledge_node_id": "node_a", "question": "q1",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 30, "difficulty": 3},
        ]
        result = analyze_session(records, masteries={"node_a": 0.8})
        assert len(result["mastery_updates"]) >= 1
        update = result["mastery_updates"][0]
        assert update["new_mastery"] < update["old_mastery"]

    def test_per_node_breakdown(self):
        records = [
            {"knowledge_node_id": "a", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
            {"knowledge_node_id": "b", "question": "q2",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 20, "difficulty": 3},
        ]
        result = analyze_session(records, {})
        assert len(result["per_node"]) == 2
        for pn in result["per_node"]:
            assert "accuracy" in pn
            assert "knowledge_node_id" in pn

    def test_weak_node_threshold(self):
        records = [
            {"knowledge_node_id": "weak", "question": "q1",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 10, "difficulty": 1},
        ]
        result = analyze_session(records, masteries={"weak": 0.3})
        assert len(result["weak_nodes"]) >= 1

    def test_strong_node_threshold(self):
        records = [
            {"knowledge_node_id": "strong", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 1},
        ]
        result = analyze_session(records, masteries={"strong": 0.5})
        assert len(result["strengths"]) >= 1

    def test_mastery_events_output(self):
        records = [
            {"knowledge_node_id": "n1", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
        ]
        result = analyze_session(records, {})
        assert "mastery_events" in result
        for event in result["mastery_events"]:
            assert "node_id" in event
            assert "event_type" in event


class TestGetDashboard:
    def test_empty_dashboard(self):
        result = get_dashboard(1, {}, [])
        assert result["total_exercises_done"] == 0
        assert result["avg_accuracy"] == 0
        assert result["avg_mastery"] == 0
        assert result["weak_nodes"] == []
        assert result["strong_nodes"] == []

    def test_dashboard_with_records(self):
        records = [
            {"knowledge_node_id": "n1", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
            {"knowledge_node_id": "n1", "question": "q2",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 20, "difficulty": 2},
        ]
        result = get_dashboard(1, {"n1": 0.5}, records)
        assert result["total_exercises_done"] == 2
        assert result["avg_accuracy"] == 50
        assert result["avg_mastery"] == 0.5

    def test_dashboard_recommended_nodes(self):
        records = [
            {"knowledge_node_id": "weak_node", "question": "q1",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 10, "difficulty": 1},
        ]
        result = get_dashboard(1, {}, records)
        assert len(result["recommended_nodes"]) >= 1
        assert result["recommended_nodes"][0]["knowledge_node_id"] == "weak_node"

    def test_strong_nodes_threshold(self):
        records = [
            {"knowledge_node_id": "good", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
        ]
        result = get_dashboard(1, {}, records)
        assert len(result["strong_nodes"]) >= 1

    def test_multiple_nodes_aggregation(self):
        records = [
            {"knowledge_node_id": "n1", "question": "q1",
             "question_type": "choice", "user_answer": "A", "correct_answer": "A",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
            {"knowledge_node_id": "n2", "question": "q2",
             "question_type": "choice", "user_answer": "X", "correct_answer": "Y",
             "is_correct": False, "time_spent_seconds": 10, "difficulty": 2},
            {"knowledge_node_id": "n2", "question": "q3",
             "question_type": "choice", "user_answer": "B", "correct_answer": "B",
             "is_correct": True, "time_spent_seconds": 10, "difficulty": 2},
        ]
        result = get_dashboard(1, {"n1": 0.7, "n2": 0.4}, records)
        assert result["total_exercises_done"] == 3
