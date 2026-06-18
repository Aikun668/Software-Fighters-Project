"""Tests for DeepTutor-style entry-based profile system.

覆盖:
- Entry model: 新条目创建 + 相似条目置信度累积 + 状态晋升
- Entry trim: 超出上限按状态/置信度裁剪
- Stability counter: REPLACE 维度需连续 N 次确认才替换（不变）
- NUMBER EMA: knowledge_base 行为不变
- Backward compat: 旧版 list 字段按置信度降序同步
- _merge_in_memory: 内存降级路径行为一致
- Edge cases: 空 fragment、None 值、无效类型
"""

import pytest
from unittest.mock import MagicMock

from app.agents.profile_agent import (
    ProfileAgent,
    STABILITY_N,
    MAX_ENTRIES_PER_DIM,
    MIN_CONFIDENCE_FOR_ACTIVE,
    ARRAY_DIMENSIONS,
    REPLACE_DIMENSIONS,
    NUMBER_DIMENSIONS,
)


def _make_mock_profile(**kwargs):
    p = MagicMock()
    p.knowledge_base = kwargs.get("knowledge_base", 0)
    p.cognitive_style = kwargs.get("cognitive_style")
    p.learning_goal = kwargs.get("learning_goal")
    p.weak_points = kwargs.get("weak_points", [])
    p.learning_pace = kwargs.get("learning_pace")
    p.interest_direction = kwargs.get("interest_direction", [])
    p.tag_weights = kwargs.get("tag_weights", {})
    p.stability_counter = kwargs.get("stability_counter", {})
    p.entries = kwargs.get("entries", {})
    return p


# ── 条目模型 ARRAY 维度 ─────────────────────────────────────────


class TestEntryModel:
    """ARRAY 维度：条目模型（置信度 + 状态 + 去重）"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_new_entry_creates_tentative(self, agent):
        """新条目 → confidence=1, status=tentative"""
        p = _make_mock_profile()
        fragment = {"weak_points": [{"text": "学生对链式求导的计算步骤不熟悉"}]}

        agent._apply_merge(p, fragment)

        entries = p.entries
        assert "weak_points" in entries
        assert len(entries["weak_points"]) == 1
        e = entries["weak_points"][0]
        assert e["text"] == "学生对链式求导的计算步骤不熟悉"
        assert e["confidence"] == 1
        assert e["status"] == "tentative"

    def test_entry_from_plain_string(self, agent):
        """LLM 输出纯字符串时同样处理"""
        p = _make_mock_profile()
        fragment = {"weak_points": ["线性代数基础薄弱"]}

        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert len(entries) == 1
        assert entries[0]["text"] == "线性代数基础薄弱"
        assert entries[0]["confidence"] == 1

    def test_similar_entry_boosts_confidence(self, agent):
        """bigram 相似的条目 → 置信度 +1，不创建新条目"""
        p = _make_mock_profile(entries={
            "weak_points": [{
                "text": "学生对反向传播的链式求导有困难",
                "confidence": 1,
                "status": "tentative",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }]
        })

        # LLM 再次提取出相似表述
        fragment = {"weak_points": [
            {"text": "学生对反向传播的链式求导理解不深，反复出错"}
        ]}

        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert len(entries) == 1  # 没有创建新条目
        assert entries[0]["confidence"] == 2

    def test_entry_promoted_to_active(self, agent):
        """confidence >= MIN_CONFIDENCE_FOR_ACTIVE → status = active"""
        p = _make_mock_profile(entries={
            "weak_points": [{
                "text": "微积分基础薄弱，尤其多元函数部分",
                "confidence": MIN_CONFIDENCE_FOR_ACTIVE - 1,
                "status": "tentative",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }]
        })

        fragment = {"weak_points": [{"text": "微积分基础薄弱，尤其多元函数部分"}]}

        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert entries[0]["confidence"] == MIN_CONFIDENCE_FOR_ACTIVE
        assert entries[0]["status"] == "active"

    def test_dissimilar_entry_creates_new(self, agent):
        """不相似的条目 → 创建新条目"""
        p = _make_mock_profile(entries={
            "weak_points": [{
                "text": "数学基础薄弱",
                "confidence": 2,
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }]
        })

        fragment = {"weak_points": [{"text": "写代码时经常出现缩进错误"}]}

        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert len(entries) == 2
        assert any(e["text"] == "写代码时经常出现缩进错误" for e in entries)
        assert any(e["text"] == "数学基础薄弱" for e in entries)

    def test_multiple_dimensions_independent(self, agent):
        """weak_points 和 interest_direction 互不干扰"""
        p = _make_mock_profile()
        fragment = {
            "weak_points": [{"text": "概率论概念混淆"}],
            "interest_direction": [{"text": "NLP方向兴趣浓厚"}],
        }

        agent._apply_merge(p, fragment)

        entries = p.entries
        assert "weak_points" in entries
        assert "interest_direction" in entries
        assert entries["weak_points"][0]["text"] == "概率论概念混淆"
        assert entries["interest_direction"][0]["text"] == "NLP方向兴趣浓厚"


class TestEntryTrim:
    """条目裁剪：超出上限按优先级淘汰"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_trim_to_max_entries(self, agent):
        """超过 MAX_ENTRIES_PER_DIM → 裁剪"""
        # 构造超出上限的条目
        many_entries = [
            {
                "text": f"知识点{i}不熟悉",
                "confidence": 1,
                "status": "tentative",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }
            for i in range(MAX_ENTRIES_PER_DIM + 3)
        ]
        p = _make_mock_profile(entries={"weak_points": many_entries})

        # 新增一个条目触发裁剪
        fragment = {"weak_points": [{"text": "全新的高价值知识点"}]}
        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert len(entries) == MAX_ENTRIES_PER_DIM

    def test_trim_prioritizes_active_over_tentative(self, agent):
        """裁剪时 active > tentative"""
        entries_data = []
        for i in range(MAX_ENTRIES_PER_DIM):
            entries_data.append({
                "text": f"active条目{i}",
                "confidence": 2,
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            })
        # 加一个 tentative
        entries_data.append({
            "text": "tentative条目要被裁掉",
            "confidence": 1,
            "status": "tentative",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        })

        p = _make_mock_profile(entries={"weak_points": entries_data})

        # 新增一个条目触发裁剪
        fragment = {"weak_points": [{"text": "新条目触发裁剪"}]}
        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        assert len(entries) == MAX_ENTRIES_PER_DIM
        # tentative 应该被裁掉
        assert not any("tentative条目要被裁掉" in e["text"] for e in entries)

    def test_trim_prioritizes_high_confidence(self, agent):
        """同状态按置信度降序保留"""
        entries_data = []
        for i in range(MAX_ENTRIES_PER_DIM + 1):
            entries_data.append({
                "text": f"条目{i} c={i + 1}",
                "confidence": i + 1,
                "status": "tentative",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            })

        p = _make_mock_profile(entries={"weak_points": entries_data})
        fragment = {"weak_points": [{"text": "额外触发"}]}
        agent._apply_merge(p, fragment)

        entries = p.entries["weak_points"]
        # 最低 confidence 的被裁掉
        min_remaining = min(e["confidence"] for e in entries)
        assert min_remaining > 1  # c=1 的被裁掉了


class TestEntryEdgeCases:
    """条目模型边界情况"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_empty_fragment_no_change(self, agent):
        p = _make_mock_profile(entries={
            "weak_points": [{
                "text": "数学基础薄弱",
                "confidence": 2,
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }]
        })
        fragment = {}

        changed = agent._apply_merge(p, fragment)

        assert changed is False
        entries = p.entries["weak_points"]
        assert len(entries) == 1

    def test_none_fragment_dimension_skipped(self, agent):
        p = _make_mock_profile()
        fragment = {"weak_points": None, "interest_direction": [{"text": "对AI方向感兴趣"}]}

        changed = agent._apply_merge(p, fragment)

        entries = p.entries
        assert "weak_points" not in entries or not entries["weak_points"]
        assert "interest_direction" in entries
        assert entries["interest_direction"][0]["text"] == "对AI方向感兴趣"

    def test_empty_list_fragment_skipped(self, agent):
        p = _make_mock_profile()
        fragment = {"weak_points": []}

        changed = agent._apply_merge(p, fragment)

        assert changed is False

    def test_confidence_capped_at_10(self, agent):
        """confidence 不会无限增长"""
        p = _make_mock_profile(entries={
            "weak_points": [{
                "text": "数学薄弱",
                "confidence": 10,
                "status": "active",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            }]
        })

        fragment = {"weak_points": [{"text": "数学薄弱"}]}
        agent._apply_merge(p, fragment)

        assert p.entries["weak_points"][0]["confidence"] == 10  # 不再增长


# ── NUMBER 维度 EMA（不变）───────────────────────────────────────


class TestNumberDimension:
    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_knowledge_base_ema_unchanged(self, agent):
        p = _make_mock_profile(knowledge_base=60)
        fragment = {"knowledge_base": 80}

        changed = agent._apply_merge(p, fragment)

        # 60 * 0.7 + 80 * 0.3 = 42 + 24 = 66
        assert p.knowledge_base == 66
        assert changed is True

    def test_knowledge_base_from_none(self, agent):
        p = _make_mock_profile(knowledge_base=None)
        fragment = {"knowledge_base": 50}

        agent._apply_merge(p, fragment)

        assert p.knowledge_base == 50

    def test_knowledge_base_invalid_value_skipped(self, agent):
        p = _make_mock_profile(knowledge_base=60)
        fragment = {"knowledge_base": "不是数字"}

        changed = agent._apply_merge(p, fragment)

        assert p.knowledge_base == 60
        assert changed is False


# ── REPLACE 维度：稳定性计数器（不变）──────────────────────────


class TestStabilityCounter:
    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_first_sighting_not_replaced(self, agent):
        """contradiction 路径：首次出现矛盾不直接替换，count=1"""
        p = _make_mock_profile(cognitive_style="视觉型")
        fragment = {"cognitive_style": "项目实战驱动学习"}

        agent._apply_merge(p, fragment)

        assert p.cognitive_style == "视觉型"
        assert p.stability_counter["cognitive_style"]["count"] == 1

    def test_consecutive_same_value_replaces(self, agent):
        """contradiction 路径：连续 2 次相同矛盾值触发替换"""
        p = _make_mock_profile(cognitive_style="视觉型")

        for _ in range(STABILITY_N):
            agent._apply_merge(p, {"cognitive_style": "项目实战驱动学习"})

        assert p.cognitive_style == "项目实战驱动学习"
        assert p.stability_counter["cognitive_style"]["count"] == 0

    def test_interrupted_sequence_resets(self, agent):
        """contradiction 路径：不同矛盾值打断计数重置"""
        p = _make_mock_profile(cognitive_style="视觉型")

        agent._apply_merge(p, {"cognitive_style": "项目实战驱动学习"})
        assert p.stability_counter["cognitive_style"]["count"] == 1

        agent._apply_merge(p, {"cognitive_style": "纯理论推导式学习"})
        assert p.stability_counter["cognitive_style"]["count"] == 1
        assert p.stability_counter["cognitive_style"]["pending_value"] == "纯理论推导式学习"

        agent._apply_merge(p, {"cognitive_style": "纯理论推导式学习"})
        agent._apply_merge(p, {"cognitive_style": "纯理论推导式学习"})
        assert p.cognitive_style == "纯理论推导式学习"


# ── 向后兼容：旧版 list 字段同步 ─────────────────────────────────


class TestBackwardCompat:
    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_weak_points_sorted_by_confidence(self, agent):
        """旧版 weak_points list 按置信度降序"""
        p = _make_mock_profile()

        # 添加多个语义显著不同的条目
        agent._apply_merge(p, {"weak_points": [
            {"text": "数学基础薄弱"}, {"text": "编程能力不足"}, {"text": "英语阅读文献困难"}
        ]})
        # 再次命中前两个条目，提升置信度
        agent._apply_merge(p, {"weak_points": [
            {"text": "数学基础薄弱"}, {"text": "编程能力不足"}
        ]})

        legacy = p.weak_points
        assert legacy[0] in ("数学基础薄弱", "编程能力不足")  # 置信度高，排前面
        assert "英语阅读文献困难" in legacy  # 仍然在列表中

    def test_empty_entries_preserved(self, agent):
        """空 entries 不破坏已有数据"""
        p = _make_mock_profile(weak_points=["已有标签"], entries={})
        fragment = {}

        agent._apply_merge(p, fragment)

        assert p.weak_points == ["已有标签"]


# ── 内存降级路径 ─────────────────────────────────────────────────


class TestMemoryMerge:
    @pytest.fixture
    def agent(self):
        return ProfileAgent()

    def test_memory_merge_entry_model(self, agent):
        old = {}
        fragment = {"weak_points": [
            {"text": "微积分基础薄弱"}, {"text": "概率论概念不清"}
        ]}

        merged, changed = agent._merge_in_memory(old, fragment)

        assert changed is True
        entries = merged["entries"]["weak_points"]
        assert len(entries) == 2
        assert all(e["confidence"] == 1 for e in entries)
        assert all(e["status"] == "tentative" for e in entries)
        # 旧版向后兼容
        assert set(merged["weak_points"]) == {"微积分基础薄弱", "概率论概念不清"}

    def test_memory_merge_boosts_existing(self, agent):
        old = {
            "entries": {
                "weak_points": [{
                    "text": "微积分基础薄弱",
                    "confidence": 1,
                    "status": "tentative",
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                }]
            }
        }
        fragment = {"weak_points": [{"text": "微积分基础薄弱，尤其多元函数"}]}

        merged, changed = agent._merge_in_memory(old, fragment)

        entries = merged["entries"]["weak_points"]
        assert len(entries) == 1  # 相似条目被合并
        assert entries[0]["confidence"] == 2
        assert entries[0]["status"] == "active"

    def test_memory_merge_stability(self, agent):
        old = {"stability_counter": {"cognitive_style": {"value": "视觉型", "count": 2}}}
        fragment = {"cognitive_style": "视觉型"}

        merged, changed = agent._merge_in_memory(old, fragment)

        assert merged["cognitive_style"] == "视觉型"
        assert merged["stability_counter"]["cognitive_style"]["count"] == 0

    def test_memory_merge_numeric_ema(self, agent):
        old = {"knowledge_base": 50}
        fragment = {"knowledge_base": 90}

        merged, changed = agent._merge_in_memory(old, fragment)

        assert merged["knowledge_base"] == 62  # 50*0.7 + 90*0.3 = 62
