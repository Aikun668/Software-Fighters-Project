"""T4-B 复合表达识别（detect_compound_order）契约。

只锁确定性规则函数的行为：明确的复合连接词切成按用户表达顺序的子句，
识别不到则返回 None。此函数不改任何路由结果，仅供排序参考。
"""

import pytest

from app.services.semantic_router import detect_compound_order


class TestDetectCompoundOrder:
    def test_xian_zai(self):
        r = detect_compound_order("先帮我讲讲快排，再给我几道练习题")
        assert r == ["帮我讲讲快排", "给我几道练习题"]

    def test_ranhou(self):
        r = detect_compound_order("解释一下什么是B+树，然后出5道题")
        assert r == ["解释一下什么是B+树", "出5道题"]

    def test_shunbian(self):
        r = detect_compound_order("出5道题，顺便把知识点做成知识图谱")
        assert r == ["出5道题", "把知识点做成知识图谱"]

    def test_bing_ju_li(self):
        r = detect_compound_order("帮我找资料，再制定一个学习计划")
        assert r == ["帮我找资料", "制定一个学习计划"]

    def test_wai_jia(self):
        r = detect_compound_order("给我一份讲义，外加10道练习题")
        assert r == ["给我一份讲义", "10道练习题"]

    def test_no_compound_returns_none(self):
        assert detect_compound_order("什么是进程调度") is None
        assert detect_compound_order("帮我出5道进程调度选择题") is None
        assert detect_compound_order("") is None

    def test_three_parts_not_over_split(self):
        # 只切一次（两个子句），不强拆三个
        r = detect_compound_order("先讲讲快排，再给我几道题，顺便出点难的")
        assert r is not None and len(r) == 2
