import pytest
from unittest.mock import AsyncMock

from app.services.knowledge_extraction import extract_knowledge_nodes


class TestKnowledgeExtraction:
    @pytest.mark.asyncio
    async def test_extract_returns_empty_on_bad_llm_response(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="not valid json {{[")
        result = await extract_knowledge_nodes(
            course_id="ai_intro",
            user_message="What is backprop?",
            assistant_reply="Backprop is an algorithm.",
            existing_node_ids=[],
            llm=mock_llm,
        )
        assert result == {"primary": [], "related": [], "broad": [], "all": []}
        mock_llm.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extract_returns_groups_on_mock_llm_default(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_LLM", "true")
        result = await extract_knowledge_nodes(
            course_id="ai_intro",
            user_message="What is backprop?",
            assistant_reply="Backprop is an algorithm.",
            existing_node_ids=[],
        )
        assert isinstance(result, dict)
        assert "primary" in result
        assert "related" in result
        assert "broad" in result
        assert "all" in result

    @pytest.mark.asyncio
    async def test_extract_normalizes_valid_nodes(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"nodes": [{"id": "backprop", "name": "Backpropagation", "type": "concept", "subtype": "core", "description": "An algorithm.", "category": "intermediate", "difficulty": 3, "confidence": 0.95}]}')
        result = await extract_knowledge_nodes(
            course_id="ai_intro",
            user_message="What is backprop?",
            assistant_reply="Backprop is an algorithm.",
            existing_node_ids=[],
            llm=mock_llm,
        )
        assert len(result["all"]) == 1
        assert result["primary"][0]["id"] == "backprop"
        assert result["primary"][0]["subtype"] == "core"
        assert result["primary"][0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_extract_groups_core_related_broad(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"nodes": ['
            '{"id": "backprop", "name": "反向传播", "type": "concept", "subtype": "core", "description": "...", "category": "intermediate", "difficulty": 3, "confidence": 0.95},'
            '{"id": "chainrule", "name": "链式法则", "type": "concept", "subtype": "related", "description": "...", "category": "foundational", "difficulty": 2, "confidence": 0.9},'
            '{"id": "deeplearning", "name": "深度学习", "type": "concept", "subtype": "broad", "description": "...", "category": "foundational", "difficulty": 1, "confidence": 0.9}'
        ']}')
        result = await extract_knowledge_nodes(
            course_id="ai_intro",
            user_message="What is backprop?",
            assistant_reply="Backprop uses chain rule in deep learning.",
            existing_node_ids=[],
            llm=mock_llm,
        )
        assert len(result["primary"]) == 1
        assert len(result["related"]) == 1
        assert len(result["broad"]) == 1
        assert result["primary"][0]["id"] == "backprop"
        assert result["related"][0]["id"] == "chainrule"
        assert result["broad"][0]["id"] == "deeplearning"

    @pytest.mark.asyncio
    async def test_extract_defaults_missing_subtype_to_related(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"nodes": [{"id": "backprop", "name": "Backpropagation", "type": "concept", "description": "An algorithm.", "category": "intermediate", "difficulty": 3, "confidence": 0.95}]}')
        result = await extract_knowledge_nodes(
            course_id="ai_intro",
            user_message="What is backprop?",
            assistant_reply="Backprop is an algorithm.",
            existing_node_ids=[],
            llm=mock_llm,
        )
        assert result["related"][0]["subtype"] == "related"
        assert result["primary"] == []
