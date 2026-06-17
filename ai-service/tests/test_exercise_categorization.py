"""Tests for exercise categorization service — mock LLM."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.exercise_categorization_service import (
    categorize_exercises,
    _normalize_result,
    _fallback_results,
)


class TestNormalizeResult:
    def test_valid_result(self):
        raw = {
            "knowledge_node_id": "backprop",
            "difficulty": 3,
            "question_type": "short_answer",
            "confidence": 0.9,
        }
        result = _normalize_result(raw, 0)
        assert result["index"] == 0
        assert result["knowledge_node_id"] == "backprop"
        assert result["difficulty"] == 3
        assert result["question_type"] == "short_answer"
        assert result["confidence"] == 0.9

    def test_missing_node_id_defaults_to_unknown(self):
        result = _normalize_result({}, 0)
        assert result["knowledge_node_id"] == "unknown"

    def test_none_node_id_defaults_to_unknown(self):
        result = _normalize_result({"knowledge_node_id": None}, 0)
        assert result["knowledge_node_id"] == "unknown"

    def test_difficulty_clamped(self):
        result = _normalize_result({"difficulty": 99}, 0)
        assert result["difficulty"] == 5
        result = _normalize_result({"difficulty": -5}, 0)
        assert result["difficulty"] == 1

    def test_invalid_difficulty_defaults(self):
        result = _normalize_result({"difficulty": "abc"}, 0)
        assert result["difficulty"] == 3

    def test_invalid_question_type_defaults_to_choice(self):
        result = _normalize_result({"question_type": "essay"}, 0)
        assert result["question_type"] == "choice"

    def test_confidence_clamped(self):
        result = _normalize_result({"confidence": 99}, 0)
        assert result["confidence"] == 1.0
        result = _normalize_result({"confidence": -5}, 0)
        assert result["confidence"] == 0.0


class TestFallbackResults:
    def test_returns_unknown_for_all(self):
        exercises = [
            {"question": "q1", "question_type": "choice"},
            {"question": "q2", "question_type": "short_answer"},
        ]
        results = _fallback_results(exercises)
        assert len(results) == 2
        for r in results:
            assert r["knowledge_node_id"] == "unknown"
            assert r["confidence"] == 0.0

    def test_empty_list(self):
        assert _fallback_results([]) == []


class TestCategorizeExercises:
    @pytest.mark.asyncio
    async def test_categorize_success(self):
        llm_response = json.dumps({
            "results": [
                {"knowledge_node_id": "backprop", "difficulty": 3,
                 "question_type": "short_answer", "confidence": 0.92},
            ]
        })
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        with patch(
            "app.services.exercise_categorization_service.get_llm_service",
            return_value=mock_llm,
        ):
            results = await categorize_exercises(
                [{"question": "什么是反向传播？", "question_type": "short_answer"}],
                [{"id": "backprop", "name": "反向传播", "description": "梯度计算算法"}],
            )
        assert len(results) == 1
        assert results[0]["knowledge_node_id"] == "backprop"
        assert results[0]["difficulty"] == 3
        assert results[0]["confidence"] == 0.92

    @pytest.mark.asyncio
    async def test_categorize_llm_failure_fallback(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM down"))

        with patch(
            "app.services.exercise_categorization_service.get_llm_service",
            return_value=mock_llm,
        ):
            results = await categorize_exercises(
                [{"question": "test", "question_type": "choice"}],
                [{"id": "n1", "name": "Node1", "description": "desc"}],
            )
        assert len(results) == 1
        assert results[0]["knowledge_node_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_categorize_non_json_response_fallback(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="just some plain text, no JSON")

        with patch(
            "app.services.exercise_categorization_service.get_llm_service",
            return_value=mock_llm,
        ):
            results = await categorize_exercises(
                [{"question": "test", "question_type": "choice"}],
                [{"id": "n1", "name": "Node1", "description": "desc"}],
            )
        assert len(results) == 1
        assert results[0]["knowledge_node_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_categorize_empty_exercises(self):
        results = await categorize_exercises([], [])
        assert results == []

    @pytest.mark.asyncio
    async def test_categorize_missing_indices_filled(self):
        llm_response = json.dumps({
            "results": [
                {"knowledge_node_id": "n1", "difficulty": 2,
                 "question_type": "choice", "confidence": 0.8},
            ]
        })
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        with patch(
            "app.services.exercise_categorization_service.get_llm_service",
            return_value=mock_llm,
        ):
            results = await categorize_exercises(
                [
                    {"question": "q1", "question_type": "choice"},
                    {"question": "q2", "question_type": "short_answer"},
                ],
                [{"id": "n1", "name": "Node1", "description": "desc"}],
            )
        assert len(results) == 2
        indices = {r["index"] for r in results}
        assert indices == {0, 1}
        # Second exercise should get fallback since LLM only returned 1 result
        unknown = [r for r in results if r["knowledge_node_id"] == "unknown"]
        assert len(unknown) == 1
