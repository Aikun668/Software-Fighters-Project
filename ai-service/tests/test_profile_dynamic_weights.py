"""Tests for dynamic profile weight system.

覆盖:
- Tag EMA: 新标签初始权重 + 重复出现权重上升
- Tag decay: 未命中标签权重衰减 + 低于阈值自动清除
- Stability counter: REPLACE 维度需连续 N 次确认才替换
- Backward compat: 旧版 list 字段按权重降序同步
- _merge_in_memory: 内存降级路径行为一致
- Edge cases: 空 fragment、None 值、无效类型
"""

import pytest
from unittest.mock import MagicMock

from app.agents.profile_agent import (
    ProfileAgent,
    TAG_EMA_ALPHA,
    TAG_CUTOFF,
    STABILITY_N,
    ARRAY_DIMENSIONS,
    REPLACE_DIMENSIONS,
    NUMBER_DIMENSIONS,
)


def _make_mock_profile(**kwargs):
    """创建模拟 ORM 对象"""
    p = MagicMock()
    p.knowledge_base = kwargs.get("knowledge_base", 0)
    p.cognitive_style = kwargs.get("cognitive_style")
    p.learning_goal = kwargs.get("learning_goal")
    p.weak_points = kwargs.get("weak_points", [])
    p.learning_pace = kwargs.get("learning_pace")
    p.interest_direction = kwargs.get("interest_direction", [])
    p.tag_weights = kwargs.get("tag_weights", {})
    p.stability_counter = kwargs.get("stability_counter", {})
    return p


class TestTagEmaWeights:
    """ARRAY 维度：标签 EMA 权重"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_new_tag_gets_initial_weight(self, agent):
        """新标签第一次出现获得 TAG_EMA_ALPHA 作为初始权重"""
        p = _make_mock_profile()
        fragment = {"weak_points": ["线性代数"]}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights
        assert "weak_points" in tw
        assert tw["weak_points"]["线性代数"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)

    def test_repeated_tag_ema_boost(self, agent):
        """多次出现 → EMA 向 1.0 收敛"""
        p = _make_mock_profile()

        # 第一次
        agent._apply_merge(p, {"weak_points": ["线性代数"]})
        w1 = p.tag_weights["weak_points"]["线性代数"]
        assert w1 == pytest.approx(TAG_EMA_ALPHA, abs=0.01)

        # 第二次（模拟新一轮提取也包含此标签）
        agent._apply_merge(p, {"weak_points": ["线性代数"]})
        w2 = p.tag_weights["weak_points"]["线性代数"]
        expected = round(w1 * (1 - TAG_EMA_ALPHA) + TAG_EMA_ALPHA, 2)
        assert w2 == pytest.approx(expected, abs=0.02)
        assert w2 > w1  # 权重上升

    def test_multiple_tags_independent_weights(self, agent):
        """多个标签各自独立维护权重"""
        p = _make_mock_profile()
        fragment = {"interest_direction": ["深度学习", "NLP"]}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights["interest_direction"]
        assert len(tw) == 2
        assert tw["深度学习"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)
        assert tw["NLP"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)

    def test_two_dimensions_independent(self, agent):
        """weak_points 和 interest_direction 互不干扰"""
        p = _make_mock_profile()
        agent._apply_merge(p, {
            "weak_points": ["数学"],
            "interest_direction": ["AI"],
        })

        tw = p.tag_weights
        assert "weak_points" in tw
        assert "interest_direction" in tw
        assert tw["weak_points"]["数学"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)
        assert tw["interest_direction"]["AI"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)


class TestTagDecay:
    """ARRAY 维度：标签衰减 + 自动清除"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_unseen_tag_decays(self, agent):
        """前一轮有、本轮无 → 衰减"""
        p = _make_mock_profile(tag_weights={
            "weak_points": {"线性代数": 0.8}
        })
        fragment = {"weak_points": ["微积分"]}  # 线性代数不在本轮

        agent._apply_merge(p, fragment)

        tw = p.tag_weights["weak_points"]
        decayed = round(0.8 * (1 - TAG_EMA_ALPHA), 2)
        assert tw["线性代数"] == decayed
        assert tw["微积分"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)

    def test_tag_below_cutoff_removed(self, agent):
        """衰减到低于 TAG_CUTOFF → 自动删除"""
        near_cutoff = TAG_CUTOFF / 2  # 下一轮衰减必定低于 cutoff
        p = _make_mock_profile(tag_weights={
            "weak_points": {"旧标签": near_cutoff}
        })
        fragment = {"weak_points": ["新标签"]}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights["weak_points"]
        assert "旧标签" not in tw  # 已被清除
        assert "新标签" in tw

    def test_tag_at_cutoff_decays_below_and_removed(self, agent):
        """恰好等于 cutoff 的标签衰减后低于 cutoff → 自动删除"""
        exactly_cutoff = TAG_CUTOFF
        p = _make_mock_profile(tag_weights={
            "weak_points": {"边界标签": exactly_cutoff}
        })
        # 本轮只出现其他标签 → 边界标签触发衰减
        fragment = {"weak_points": ["其他标签"]}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights.get("weak_points", {})
        assert "边界标签" not in tw  # 衰减后 < cutoff，被清除
        assert "其他标签" in tw

    def test_empty_fragment_does_not_clear(self, agent):
        """空 fragment 不触发任何权重变化"""
        p = _make_mock_profile(tag_weights={
            "weak_points": {"数学": 0.8}
        })
        fragment = {}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights["weak_points"]
        assert tw["数学"] == 0.8  # 保持不变

    def test_fragment_with_none_value_skipped(self, agent):
        """fragment 中值为 None 的维度被跳过"""
        p = _make_mock_profile()
        fragment = {"weak_points": None, "interest_direction": ["AI"]}

        agent._apply_merge(p, fragment)

        tw = p.tag_weights
        assert "weak_points" not in tw  # None 被跳过
        assert "interest_direction" in tw


class TestStabilityCounter:
    """REPLACE 维度：稳定性门控"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_first_sighting_not_replaced(self, agent):
        """第一次出现的新值：stability_counter 计数但不替换"""
        p = _make_mock_profile(cognitive_style="视觉型")
        fragment = {"cognitive_style": "听觉型"}

        changed = agent._apply_merge(p, fragment)

        assert p.cognitive_style == "视觉型"  # 值未改变
        assert changed is True  # stability_counter 变更
        assert p.stability_counter["cognitive_style"]["count"] == 1

    def test_consecutive_same_value_replaces(self, agent):
        """连续 STABILITY_N 次相同值 → 实际替换"""
        p = _make_mock_profile(cognitive_style="视觉型")

        # 连续出现 N 次
        for i in range(STABILITY_N):
            changed = agent._apply_merge(p, {"cognitive_style": "听觉型"})

        assert p.cognitive_style == "听觉型"  # 已替换
        assert p.stability_counter["cognitive_style"]["count"] == 0  # reset

    def test_interrupted_sequence_resets(self, agent):
        """中间出现不同值 → 计数器重置"""
        p = _make_mock_profile(cognitive_style="视觉型")

        # 第一次: "听觉型"
        agent._apply_merge(p, {"cognitive_style": "听觉型"})
        assert p.stability_counter["cognitive_style"]["count"] == 1

        # 第二次: 不同值 → 重置
        agent._apply_merge(p, {"cognitive_style": "读写型"})
        assert p.stability_counter["cognitive_style"]["count"] == 1
        assert p.stability_counter["cognitive_style"]["value"] == "读写型"

        # 再连续 3 次
        agent._apply_merge(p, {"cognitive_style": "读写型"})
        agent._apply_merge(p, {"cognitive_style": "读写型"})
        assert p.cognitive_style == "读写型"  # 第 3 次替换

    def test_same_value_no_change(self, agent):
        """当前值已等于新值 → counter 累加但值不变"""
        p = _make_mock_profile(cognitive_style="视觉型")
        p.stability_counter = {"cognitive_style": {"value": "视觉型", "count": 2}}

        changed = agent._apply_merge(p, {"cognitive_style": "视觉型"})

        assert p.cognitive_style == "视觉型"  # 值不变
        assert p.stability_counter["cognitive_style"]["count"] == 3
        assert changed is True  # stability_counter 变更了


class TestNumberDimension:
    """NUMBER 维度：EMA 行为不变"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_knowledge_base_ema_unchanged(self, agent):
        """knowledge_base 仍然使用 EMA 合并"""
        p = _make_mock_profile(knowledge_base=60)
        fragment = {"knowledge_base": 80}

        changed = agent._apply_merge(p, fragment)

        # 60 * 0.7 + 80 * 0.3 = 42 + 24 = 66
        assert p.knowledge_base == 66
        assert changed is True

    def test_knowledge_base_from_zero(self, agent):
        """初始无值时直接用新值"""
        p = _make_mock_profile(knowledge_base=None)
        fragment = {"knowledge_base": 50}

        agent._apply_merge(p, fragment)

        assert p.knowledge_base == 50

    def test_knowledge_base_invalid_value_skipped(self, agent):
        """非数字值被跳过"""
        p = _make_mock_profile(knowledge_base=60)
        fragment = {"knowledge_base": "不是数字"}

        changed = agent._apply_merge(p, fragment)

        assert p.knowledge_base == 60  # 不变
        assert changed is False


class TestBackwardCompat:
    """向后兼容：旧版 list 字段同步"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_weak_points_sorted_by_weight(self, agent):
        """weak_points 按权重降序同步到旧版字段"""
        p = _make_mock_profile()

        agent._apply_merge(p, {"weak_points": ["A", "B", "C"]})  # 全是 0.4
        agent._apply_merge(p, {"weak_points": ["A", "B"]})       # A,B 0.64, C 衰减至 0.24
        agent._apply_merge(p, {"weak_points": ["A"]})            # A 0.78, B 衰减至 0.38, C 衰减至 0.14→清除

        legacy = p.weak_points
        weights = p.tag_weights["weak_points"]
        assert legacy[0] == "A"
        assert legacy == ["A", "B"]  # C 已衰减至 cutoff 以下被清除
        assert weights["A"] > weights["B"]  # 0.78 > 0.38

    def test_interest_direction_sorted_by_weight(self, agent):
        """interest_direction 同样按权重降序"""
        p = _make_mock_profile()
        agent._apply_merge(p, {"interest_direction": ["DL", "CV", "NLP"]})
        agent._apply_merge(p, {"interest_direction": ["DL"]})

        legacy = p.interest_direction
        assert legacy[0] == "DL"  # 权重最高

    def test_tag_weights_preserved_across_empty_fragment(self, agent):
        """空 fragment 不破坏已有的 tag_weights"""
        p = _make_mock_profile(tag_weights={
            "weak_points": {"数学": 0.8, "英语": 0.5}
        })

        agent._apply_merge(p, {})

        assert p.tag_weights["weak_points"]["数学"] == 0.8
        assert p.tag_weights["weak_points"]["英语"] == 0.5


class TestMemoryMerge:
    """_merge_in_memory 降级路径一致性"""

    @pytest.fixture
    def agent(self):
        return ProfileAgent(use_mock_llm=True)

    def test_memory_merge_tag_weights(self, agent):
        old = {}
        fragment = {"weak_points": ["微积分", "概率论"]}

        merged, changed = agent._merge_in_memory(old, fragment)

        assert changed is True
        # 同级权重排序不确定，用 set 比较
        assert set(merged["weak_points"]) == {"微积分", "概率论"}
        tw = merged["tag_weights"]["weak_points"]
        assert tw["微积分"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)
        assert tw["概率论"] == pytest.approx(TAG_EMA_ALPHA, abs=0.01)

    def test_memory_merge_decay(self, agent):
        old = {"tag_weights": {"weak_points": {"旧标签": 0.8}}}
        fragment = {"weak_points": ["新标签"]}

        merged, changed = agent._merge_in_memory(old, fragment)

        tw = merged["tag_weights"]["weak_points"]
        assert "旧标签" in tw  # 衰减后 = 0.48, > 0.2 保留
        assert tw["旧标签"] < 0.8  # 确实衰减了
        assert "新标签" in tw

    def test_memory_merge_stability(self, agent):
        old = {"stability_counter": {"cognitive_style": {"value": "视觉型", "count": 2}}}
        fragment = {"cognitive_style": "视觉型"}

        merged, changed = agent._merge_in_memory(old, fragment)

        # 第 3 次 → 替换
        assert merged["cognitive_style"] == "视觉型"
        assert merged["stability_counter"]["cognitive_style"]["count"] == 0

    def test_memory_merge_numeric_ema(self, agent):
        old = {"knowledge_base": 50}
        fragment = {"knowledge_base": 90}

        merged, changed = agent._merge_in_memory(old, fragment)

        # 50 * 0.7 + 90 * 0.3 = 35 + 27 = 62
        assert merged["knowledge_base"] == 62
