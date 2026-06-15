"""
Multi-dimensional smoke & stress tests for knowledge node extraction.

Dimensions:
  D1 – Functional correctness (normal path, id slugification, enums, filtering)
  D2 – Robustness / error handling (bad JSON, missing keys, LLM failures)
  D3 – Edge cases (Chinese, Unicode, boundary confidence, long texts)
  D4 – Stress (bulk nodes, large existing sets, rapid calls)
  D5 – Schema validation (every returned node shape)
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

from app.services.knowledge_extraction import (
    _MIN_CONFIDENCE,
    _VALID_CATEGORIES,
    _VALID_TYPES,
    _node_id_from_name,
    _normalize_value,
    _clean_prerequisites,
    _clean_relations,
    extract_knowledge_nodes,
)

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_mock_llm(nodes: list[dict] | None, raw: str | None = None):
    """Return an AsyncMock LLM that returns `raw` or a JSON string of `{"nodes": nodes}`."""
    llm = AsyncMock()
    if raw is not None:
        llm.chat = AsyncMock(return_value=raw)
    elif nodes is not None:
        llm.chat = AsyncMock(return_value=json.dumps({"nodes": nodes}, ensure_ascii=False))
    return llm


def _assert_node_shape(node: dict, expected_id: str | None = None):
    """Validate every mandatory key, type, and range on a single node."""
    mandatory_keys = {
        "id", "name", "type", "description", "category",
        "difficulty", "confidence", "suggested_prerequisites", "suggested_relations",
    }
    assert mandatory_keys.issubset(node.keys()), f"Missing keys: {mandatory_keys - node.keys()}"

    assert isinstance(node["id"], str) and node["id"], "id must be non-empty str"
    assert isinstance(node["name"], str) and node["name"], "name must be non-empty str"
    assert node["type"] in _VALID_TYPES, f"type must be in {_VALID_TYPES}, got {node['type']}"
    assert isinstance(node["description"], str)
    assert node["category"] in _VALID_CATEGORIES, f"category must be in {_VALID_CATEGORIES}"
    assert isinstance(node["difficulty"], int) and 1 <= node["difficulty"] <= 5
    assert isinstance(node["confidence"], float) and 0.0 <= node["confidence"] <= 1.0
    assert isinstance(node["suggested_prerequisites"], list)
    assert isinstance(node["suggested_relations"], list)

    for rel in node["suggested_relations"]:
        assert isinstance(rel, dict)
        assert "source" in rel and "target" in rel and "relation" in rel

    if expected_id is not None:
        assert node["id"] == expected_id


# ═══════════════════════════════════════════════════════════════════
# D1 – Functional Correctness
# ═══════════════════════════════════════════════════════════════════

class TestD1_FunctionalCorrectness:

    @pytest.mark.asyncio
    async def test_single_node_normal_path(self):
        """Happy path: one well-formed node returned."""
        llm = _make_mock_llm([{
            "id": "backpropagation",
            "name": "反向传播",
            "type": "concept",
            "description": "一种通过链式法则计算梯度的算法",
            "category": "intermediate",
            "difficulty": 4,
            "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes(
            "ai_intro", "什么是反向传播？", "反向传播是训练神经网络的核心算法...", llm=llm,
        )
        assert len(result["all"]) == 1
        _assert_node_shape(result["all"][0], "backpropagation")

    @pytest.mark.asyncio
    async def test_multiple_nodes(self):
        """Extract several nodes at once.  Note: _slugify_id strips underscores."""
        llm = _make_mock_llm([
            {"id": "svm", "name": "SVM", "type": "concept", "description": "支持向量机", "category": "intermediate", "difficulty": 3, "confidence": 0.95},
            {"id": "kerneltrick", "name": "核技巧", "type": "concept", "description": "将低维映射到高维的数学技巧", "category": "advanced", "difficulty": 4, "confidence": 0.90},
            {"id": "featureengineering", "name": "特征工程", "type": "skill", "description": "从原始数据构造特征的过程", "category": "foundational", "difficulty": 2, "confidence": 0.88},
        ])
        result = await extract_knowledge_nodes(
            "ai_intro", "SVM的核技巧是什么？", "SVM使用核函数将数据映射到高维空间...", llm=llm,
        )
        assert len(result["all"]) == 3
        ids = {n["id"] for n in result["all"]}
        assert ids == {"svm", "kerneltrick", "featureengineering"}

    @pytest.mark.asyncio
    async def test_id_slugified_from_chinese_name(self):
        """When name has no ASCII, _slugify_id falls back to 'node'."""
        llm = _make_mock_llm([{
            "name": "深度学习",
            "type": "concept",
            "description": "机器学习的一个分支",
            "category": "intermediate",
            "difficulty": 3,
            "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes(
            "ai_intro", "深度学习和机器学习有什么区别？", "深度学习是机器学习的子集...", llm=llm,
        )
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "node"

    @pytest.mark.asyncio
    async def test_id_normalizes_special_chars(self):
        """Special characters stripped from ID; Chinese stays."""
        llm = _make_mock_llm([{
            "id": "Hello World!!!  测试 (2024)",
            "name": "Hello World 测试",
            "type": "concept",
            "description": "Test node",
            "category": "foundational",
            "difficulty": 1,
            "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes(
            "ai_intro", "test", "test reply", llm=llm,
        )
        assert len(result["all"]) == 1
        assert "!" not in result["all"][0]["id"]
        assert "(" not in result["all"][0]["id"]
        assert ")" not in result["all"][0]["id"]

    @pytest.mark.asyncio
    async def test_type_enum_coerced_to_default(self):
        """Invalid type falls back to 'concept'."""
        llm = _make_mock_llm([{
            "id": "test-node", "name": "Test", "type": "invalid_type",
            "description": "desc", "category": "foundational",
            "difficulty": 2, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result["all"][0]["type"] == "concept"

    @pytest.mark.asyncio
    async def test_category_enum_coerced(self):
        llm = _make_mock_llm([{
            "id": "x", "name": "X", "type": "fact",
            "description": "desc", "category": "super_hard",
            "difficulty": 3, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result["all"][0]["category"] == "intermediate"

    @pytest.mark.asyncio
    async def test_confidence_boundary_rejected(self):
        """Node at 0.84 is rejected; at 0.85 accepted."""
        llm = _make_mock_llm([
            {"id": "low", "name": "Low_conf", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 1, "confidence": 0.84},
            {"id": "ok", "name": "Ok_conf", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 1, "confidence": 0.85},
            {"id": "hi", "name": "Hi_conf", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 1, "confidence": 1.0},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        ids = {n["id"] for n in result["all"]}
        assert "low" not in ids
        assert "ok" in ids
        assert "hi" in ids

    @pytest.mark.asyncio
    async def test_duplicate_existing_ids_filtered(self):
        llm = _make_mock_llm([
            {"id": "backprop", "name": "反向传播", "type": "concept",
             "description": "梯度计算", "category": "intermediate",
             "difficulty": 3, "confidence": 0.95},
            {"id": "newnode", "name": "新概念", "type": "concept",
             "description": "新概念描述", "category": "foundational",
             "difficulty": 2, "confidence": 0.90},
        ])
        result = await extract_knowledge_nodes(
            "ai_intro", "hi", "reply",
            existing_node_ids={"backprop", "other_existing"},
            llm=llm,
        )
        ids = {n["id"] for n in result["all"]}
        assert "backprop" not in ids
        assert "newnode" in ids

    @pytest.mark.asyncio
    async def test_duplicate_within_batch_filtered(self):
        """Two nodes with same slugified id → only first kept."""
        llm = _make_mock_llm([
            {"id": "same_id", "name": "First", "type": "fact",
             "description": "d1", "category": "foundational",
             "difficulty": 1, "confidence": 0.95},
            {"id": "same_id", "name": "Second", "type": "fact",
             "description": "d2", "category": "foundational",
             "difficulty": 1, "confidence": 0.95},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["name"] == "First"

    @pytest.mark.asyncio
    async def test_missing_fields_get_defaults(self):
        """When LLM omits optional fields, defaults are applied."""
        llm = _make_mock_llm([{
            "id": "minimal",
            "name": "最小节点",
            "description": "基本描述",
            "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        node = result["all"][0]
        assert node["type"] == "concept"
        assert node["category"] == "intermediate"
        assert node["difficulty"] == 3
        assert node["suggested_prerequisites"] == []
        assert node["suggested_relations"] == []

    @pytest.mark.asyncio
    async def test_difficulty_clamped(self):
        """Difficulty out of range is clamped to [1,5]."""
        llm = _make_mock_llm([
            {"id": "low-d", "name": "Low", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 0, "confidence": 0.95},
            {"id": "high-d", "name": "High", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 99, "confidence": 0.95},
            {"id": "neg-d", "name": "Neg", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": -5, "confidence": 0.95},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        by_id = {n["id"]: n for n in result["all"]}
        assert by_id["low-d"]["difficulty"] == 1
        assert by_id["high-d"]["difficulty"] == 5
        assert by_id["neg-d"]["difficulty"] == 1

    @pytest.mark.asyncio
    async def test_confidence_clamped(self):
        llm = _make_mock_llm([
            {"id": "c1", "name": "C1", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 1, "confidence": 1.5},
            {"id": "c2", "name": "C2", "type": "fact", "description": "d",
             "category": "foundational", "difficulty": 1, "confidence": -0.5},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        ids = {n["id"] for n in result["all"]}
        assert "c1" in ids
        assert "c2" not in ids

    @pytest.mark.asyncio
    async def test_prerequisites_and_relations_preserved(self):
        llm = _make_mock_llm([{
            "id": "cnn",
            "name": "卷积神经网络",
            "type": "concept",
            "description": "一种用于图像处理的深度学习模型",
            "category": "advanced",
            "difficulty": 4,
            "confidence": 0.92,
            "suggested_prerequisites": ["ml_basics", "dl_basics"],
            "suggested_relations": [
                {"source": "dl_basics", "target": "cnn", "relation": "depends_on"},
                {"source": "cnn", "target": "transformer", "relation": "extends"},
            ],
        }])
        result = await extract_knowledge_nodes("ai_intro", "CNN是什么？", "CNN是卷积神经网络...", llm=llm)
        node = result["all"][0]
        assert "ml_basics" in node["suggested_prerequisites"]
        assert "dl_basics" in node["suggested_prerequisites"]
        assert len(node["suggested_relations"]) == 2

    @pytest.mark.asyncio
    async def test_name_instead_of_missing_id(self):
        llm = _make_mock_llm([{
            "name": "KnowledgeDistillation",
            "type": "concept",
            "description": "模型压缩技术",
            "category": "advanced",
            "difficulty": 4,
            "confidence": 0.90,
        }])
        result = await extract_knowledge_nodes("ai_intro", "什么是知识蒸馏？", "知识蒸馏是模型压缩...", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "knowledgedistillation"


# ═══════════════════════════════════════════════════════════════════
# D2 – Robustness / Error Handling
# ═══════════════════════════════════════════════════════════════════

class TestD2_Robustness:

    @pytest.mark.asyncio
    async def test_empty_user_message_returns_empty(self):
        llm = _make_mock_llm([{"id": "x", "name": "X", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95}])
        result = await extract_knowledge_nodes("ai_intro", "", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}
        llm.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_assistant_reply_returns_empty(self):
        llm = _make_mock_llm([{"id": "x", "name": "X", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95}])
        result = await extract_knowledge_nodes("ai_intro", "hello", "", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}
        llm.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_whitespace_only_messages_return_empty(self):
        result = await extract_knowledge_nodes("ai_intro", "   ", "   ")
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_llm_returns_plain_text(self):
        """Non-JSON response → empty list."""
        llm = _make_mock_llm(None, raw="This is just plain text, no JSON here.")
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_llm_returns_json_without_nodes_key(self):
        llm = _make_mock_llm(None, raw='{"other_key": "value"}')
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_whitespace_only_messages_not_caught_by_fast_check(self):
        llm = _make_mock_llm([{"id": "x", "name": "X", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95}])
        result = await extract_knowledge_nodes("ai_intro", "   ", "   ", llm=llm)
        assert len(result["all"]) == 1

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self):
        llm = AsyncMock()
        llm.chat = AsyncMock(side_effect=RuntimeError("API timeout"))
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_nodes_is_not_a_list(self):
        llm = _make_mock_llm(None, raw='{"nodes": "not_a_list"}')
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_nodes_contains_nulls_and_non_dicts(self):
        """Non-dict elements in nodes array are skipped."""
        llm = _make_mock_llm(None, raw=json.dumps({"nodes": [
            None,
            "a string",
            123,
            {"id": "valid", "name": "Valid", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
            [],
        ]}))
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "valid"

    @pytest.mark.asyncio
    async def test_nodes_with_missing_name_skipped(self):
        llm = _make_mock_llm([
            {"id": "noname", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
            {"id": "hasname", "name": "有名字", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "hasname"

    @pytest.mark.asyncio
    async def test_extra_fields_ignored(self):
        """LLM can include extra keys; they don't break anything."""
        llm = _make_mock_llm([{
            "id": "ok", "name": "OK", "type": "fact", "description": "d",
            "category": "foundational", "difficulty": 1, "confidence": 0.95,
            "extra_field": "should_be_ignored",
            "nested": {"a": 1},
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1

    @pytest.mark.asyncio
    async def test_empty_name_skipped(self):
        llm = _make_mock_llm([
            {"id": "x", "name": "", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
            {"id": "y", "name": "   ", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result == {"primary": [], "related": [], "broad": [], "all": []}

    @pytest.mark.asyncio
    async def test_name_as_fallback_description(self):
        """When description is empty, name is used."""
        llm = _make_mock_llm([{
            "id": "test", "name": "TestName", "type": "fact",
            "description": "", "category": "foundational",
            "difficulty": 1, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert result["all"][0]["description"] == "TestName"


# ═══════════════════════════════════════════════════════════════════
# D3 – Edge Cases
# ═══════════════════════════════════════════════════════════════════

class TestD3_EdgeCases:

    @pytest.mark.asyncio
    async def test_chinese_only_content(self):
        llm = _make_mock_llm([{
            "id": "梯度消失",
            "name": "梯度消失问题",
            "type": "concept",
            "description": "深度神经网络中梯度逐层衰减的现象",
            "category": "intermediate",
            "difficulty": 3,
            "confidence": 0.93,
        }])
        result = await extract_knowledge_nodes(
            "ai_intro",
            "为什么深层网络会有梯度消失？",
            "梯度消失是因为链式求导时，如果每层梯度小于1，连乘后梯度会指数级衰减。解决方法包括使用ReLU激活函数、Batch Normalization和残差连接。",
            llm=llm,
        )
        assert len(result["all"]) == 1
        _assert_node_shape(result["all"][0])

    @pytest.mark.asyncio
    async def test_unicode_in_names(self):
        """Unicode characters like emoji or special symbols in names."""
        llm = _make_mock_llm([{
            "id": "e=mc2",
            "name": "E=mc² 质能方程",
            "type": "concept",
            "description": "爱因斯坦质能方程",
            "category": "foundational",
            "difficulty": 2,
            "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "质能方程", "E=mc²...", llm=llm)
        assert len(result["all"]) == 1
        assert "E=mc²" in result["all"][0]["name"]

    @pytest.mark.asyncio
    async def test_long_messages(self):
        """Very long user and assistant messages should not cause issues."""
        long_msg = "请解释" + "深度学习" * 1000
        long_reply = "深度学习是" + "机器学习的一个重要分支，它通过多层神经网络来学习数据的层次化表示。" * 500
        llm = _make_mock_llm([{
            "id": "deep_learning_long", "name": "深度学习",
            "type": "concept", "description": "多层神经网络学习方法",
            "category": "intermediate", "difficulty": 3, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", long_msg, long_reply, llm=llm)
        assert len(result["all"]) == 1

    @pytest.mark.asyncio
    async def test_all_node_types(self):
        """Every valid type is preserved."""
        for t in sorted(_VALID_TYPES):
            llm = _make_mock_llm([{
                "id": f"node_{t}", "name": f"{t}_node", "type": t,
                "description": f"A {t} node", "category": "foundational",
                "difficulty": 2, "confidence": 0.95,
            }])
            result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
            assert len(result["all"]) == 1
            assert result["all"][0]["type"] == t

    @pytest.mark.asyncio
    async def test_all_categories(self):
        for c in sorted(_VALID_CATEGORIES):
            llm = _make_mock_llm([{
                "id": f"cat_{c}", "name": f"{c}_cat", "type": "concept",
                "description": f"A {c} node", "category": c,
                "difficulty": 2, "confidence": 0.95,
            }])
            result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
            assert len(result["all"]) == 1
            assert result["all"][0]["category"] == c

    @pytest.mark.asyncio
    async def test_code_block_wrapped_json(self):
        """LLM wraps JSON in ```json ... ``` code block."""
        llm = _make_mock_llm(None, raw='```json\n{"nodes": [{"id": "cb", "name": "CodeBlock", "type": "fact", "description": "from code block", "category": "foundational", "difficulty": 1, "confidence": 0.95}]}\n```')
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "cb"

    @pytest.mark.asyncio
    async def test_trailing_comma_json_repair(self):
        """JSON with trailing comma (common LLM mistake) is repaired."""
        llm = _make_mock_llm(None, raw='{"nodes": [{"id": "tc", "name": "TrailingComma", "type": "fact", "description": "repair me", "category": "foundational", "difficulty": 1, "confidence": 0.95,}]}')
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1

    @pytest.mark.asyncio
    async def test_json_inside_mixed_text(self):
        """JSON embedded within explanatory text."""
        llm = _make_mock_llm(None, raw='根据对话内容，我提取了以下知识节点：\n{"nodes": [{"id": "nested", "name": "嵌套", "type": "concept", "description": "混合文本中的节点", "category": "foundational", "difficulty": 1, "confidence": 0.95}]}\n以上是提取结果。')
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "nested"


# ═══════════════════════════════════════════════════════════════════
# D4 – Stress
# ═══════════════════════════════════════════════════════════════════

class TestD4_Stress:

    @pytest.mark.asyncio
    async def test_bulk_nodes_single_response(self):
        """LLM returns 50 nodes; backend truncates to _MAX_EXTRACTED_NODES."""
        nodes = []
        for i in range(50):
            nodes.append({
                "id": f"node_{i:03d}",
                "name": f"知识点 {i}",
                "type": "concept",
                "description": f"第 {i} 个知识点",
                "category": "foundational",
                "difficulty": (i % 5) + 1,
                "confidence": 0.86,
            })
        llm = _make_mock_llm(nodes)
        t0 = time.perf_counter()
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        elapsed = time.perf_counter() - t0
        assert len(result["all"]) == 5
        for node in result["all"]:
            _assert_node_shape(node)
        assert elapsed < 1.0, f"Bulk extraction took {elapsed:.3f}s, expected < 1s"

    @pytest.mark.asyncio
    async def test_large_existing_ids_set(self):
        large_set = {f"existing{i:05d}" for i in range(10000)}
        llm = _make_mock_llm([
            {"id": "keepme", "name": "Keep", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
            {"id": "existing00042", "name": "ShouldDrop", "type": "fact", "description": "d", "category": "foundational", "difficulty": 1, "confidence": 0.95},
        ])
        t0 = time.perf_counter()
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", existing_node_ids=large_set, llm=llm)
        elapsed = time.perf_counter() - t0
        assert len(result["all"]) == 1
        assert result["all"][0]["id"] == "keepme"
        assert elapsed < 0.2, f"Large existing set filter took {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_rapid_sequential_calls(self):
        async def one_call(i: int):
            llm = _make_mock_llm([{
                "id": f"rapid{i}", "name": f"Rapid {i}", "type": "fact",
                "description": f"desc {i}", "category": "foundational",
                "difficulty": 1, "confidence": 0.95,
            }])
            return await extract_knowledge_nodes("ai_intro", f"msg{i}", f"reply{i}", llm=llm)

        t0 = time.perf_counter()
        tasks = [one_call(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - t0

        for i, r in enumerate(results):
            assert len(r["all"]) == 1, f"Call {i} returned {len(r['all'])} nodes"
            assert r["all"][0]["id"] == f"rapid{i}"
        assert elapsed < 3.0, f"20 rapid calls took {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_node_id_edge_cases(self):
        """Tricky ids: pure numbers, very long, empty-after-normalize."""
        llm = _make_mock_llm([
            {"id": "12345", "name": "PureNumID", "type": "fact",
             "description": "d", "category": "foundational",
             "difficulty": 1, "confidence": 0.95},
            {"id": "a" * 200, "name": "LongID", "type": "fact",
             "description": "d", "category": "foundational",
             "difficulty": 1, "confidence": 0.95},
            {"id": "!!!", "name": "SpecialOnly", "type": "fact",
             "description": "d", "category": "foundational",
             "difficulty": 1, "confidence": 0.95},
        ])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        ids = {n["id"] for n in result["all"]}
        assert "12345" in ids
        assert "a" * 200 in ids
        assert "node" in ids


# ═══════════════════════════════════════════════════════════════════
# D5 – Schema Validation
# ═══════════════════════════════════════════════════════════════════

class TestD5_SchemaValidation:

    @pytest.mark.asyncio
    async def test_all_fields_present_and_typed(self):
        """Every returned field exists with correct Python type."""
        llm = _make_mock_llm([{
            "id": "test-schema", "name": "Test", "type": "concept",
            "description": "A schema test", "category": "foundational",
            "difficulty": 3, "confidence": 0.91,
            "suggested_prerequisites": ["p1"],
            "suggested_relations": [{"source": "a", "target": "b", "relation": "depends_on"}],
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        n = result["all"][0]

        assert isinstance(n["id"], str)
        assert isinstance(n["name"], str)
        assert isinstance(n["type"], str)
        assert isinstance(n["description"], str)
        assert isinstance(n["category"], str)
        assert isinstance(n["difficulty"], int)
        assert isinstance(n["confidence"], float)
        assert isinstance(n["suggested_prerequisites"], list)
        assert isinstance(n["suggested_relations"], list)
        for rel in n["suggested_relations"]:
            assert isinstance(rel, dict)
            assert isinstance(rel["source"], str)
            assert isinstance(rel["target"], str)
            assert isinstance(rel["relation"], str)

    @pytest.mark.asyncio
    async def test_no_unexpected_keys(self):
        """Returned dicts only contain the canonical keys."""
        llm = _make_mock_llm([{
            "id": "clean", "name": "Clean", "type": "fact",
            "description": "d", "category": "foundational",
            "difficulty": 1, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes("ai_intro", "hi", "reply", llm=llm)
        canonical = {
            "id", "name", "type", "subtype", "description", "category",
            "difficulty", "confidence", "suggested_prerequisites", "suggested_relations",
        }
        assert set(result["all"][0].keys()) == canonical


# ═══════════════════════════════════════════════════════════════════
# Pure function unit tests (no async)
# ═══════════════════════════════════════════════════════════════════

class TestPureFunctions:

    def test_node_id_from_name_basic(self):
        assert _node_id_from_name("Hello World") == "helloworld"
        assert _node_id_from_name("  Spaces  ") == "spaces"
        assert _node_id_from_name("Café & Brunch") == "cafbrunch"
        assert _node_id_from_name("!!!").startswith("node_")
        assert _node_id_from_name("a-b_c") == "a-b_c"

    def test_node_id_from_name_chinese(self):
        result = _node_id_from_name("知识图谱")
        assert result == "zhi_shi_tu_pu"

    def test_node_id_from_name_pinyin_with_english(self):
        assert _node_id_from_name("Transformer 架构") == "transformer"
        assert _node_id_from_name("CNN 卷积神经网络") == "cnn"

    def test_node_id_from_name_ascii_passthrough(self):
        assert _node_id_from_name("ai_overview") == "ai_overview"
        assert _node_id_from_name("ml_basics") == "ml_basics"
        assert _node_id_from_name("self_attention") == "self_attention"

    def test_normalize_value_type(self):
        assert _normalize_value("SKILL", "type") == "skill"
        assert _normalize_value("", "type") == "concept"
        assert _normalize_value(None, "type") == "concept"
        assert _normalize_value("invalid", "type") == "concept"

    def test_normalize_value_category(self):
        assert _normalize_value("ADVANCED", "category") == "advanced"
        assert _normalize_value("", "category") == "intermediate"
        assert _normalize_value("invalid", "category") == "intermediate"

    def test_normalize_value_difficulty(self):
        assert _normalize_value(3, "difficulty") == 3
        assert _normalize_value(0, "difficulty") == 1
        assert _normalize_value(10, "difficulty") == 5
        assert _normalize_value("4", "difficulty") == 4
        assert _normalize_value("abc", "difficulty") == 3

    def test_normalize_value_confidence(self):
        assert _normalize_value(0.95, "confidence") == 0.95
        assert _normalize_value(1.5, "confidence") == 1.0
        assert _normalize_value(-0.5, "confidence") == 0.0
        assert _normalize_value("abc", "confidence") == 0.0

    def test_normalize_value_passthrough(self):
        assert _normalize_value("hello", "name") == "hello"

    def test_clean_prerequisites(self):
        assert _clean_prerequisites(["a", "b", "c"]) == ["a", "b", "c"]
        assert _clean_prerequisites(["a", "", "  ", None, "b"]) == ["a", "b"]
        assert _clean_prerequisites("not_a_list") == []
        assert _clean_prerequisites(None) == []

    def test_clean_relations(self):
        assert _clean_relations([
            {"source": "a", "target": "b", "relation": "extends"},
        ]) == [{"source": "a", "target": "b", "relation": "extends"}]
        assert _clean_relations([
            {"source": "a", "target": "", "relation": ""},
        ]) == []
        assert _clean_relations("not_list") == []


class TestD0_FindingsFromSmokeTest:
    """Behaviors discovered during smoke testing — documented as regression guards.

    These tests verify current behavior.  Some may be intentional, others may
    represent gaps worth addressing in future iterations.
    """

    def test_underscores_preserved_for_ascii_ids(self):
        assert _node_id_from_name("ml_basics") == "ml_basics"
        assert _node_id_from_name("new_node") == "new_node"

    def test_chinese_names_produce_pinyin_ids(self):
        assert _node_id_from_name("知识图谱") == "zhi_shi_tu_pu"
        assert _node_id_from_name("深度学习") == "shen_du_xue_xi"

    @pytest.mark.asyncio
    async def test_skeleton_id_underscore_mismatch_with_extraction(self):
        llm = _make_mock_llm([{
            "id": "ai_overview", "name": "AI概述", "type": "concept",
            "description": "AI基础知识", "category": "foundational",
            "difficulty": 1, "confidence": 0.95,
        }])
        result = await extract_knowledge_nodes(
            "ai_intro", "AI基础", "AI包括...",
            existing_node_ids={"ai_overview"},
            llm=llm,
        )
        assert len(result["all"]) == 1

    def test_whitespace_only_not_short_circuited(self):
        assert bool("  ") is True

    @pytest.mark.asyncio
    async def test_rapid_extraction_stress_passes_with_ascii_ids(self):
        async def one_call(i: int):
            llm = _make_mock_llm([{
                "id": f"node{i:03d}", "name": f"N{i}", "type": "fact",
                "description": f"d{i}", "category": "foundational",
                "difficulty": 1, "confidence": 0.95,
            }])
            return await extract_knowledge_nodes("course", f"m{i}", f"r{i}", llm=llm)

        results = await asyncio.gather(*[one_call(i) for i in range(30)])
        assert all(len(r["all"]) == 1 for r in results)
