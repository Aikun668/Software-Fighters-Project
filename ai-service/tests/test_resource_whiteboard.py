"""Tests for ResourceWhiteboard — 共享上下文白板"""

import pytest

from app.workflows.resource_whiteboard import ResourceWhiteboard


class TestResourceWhiteboard:
    def test_empty_whiteboard(self):
        wb = ResourceWhiteboard()
        assert wb.topic == ""
        assert wb.key_concepts == []
        assert wb.to_context_text() == "主题: "

    def test_to_context_text_with_concepts(self):
        wb = ResourceWhiteboard(
            topic="机器学习",
            key_concepts=["监督学习", "无监督学习"],
        )
        text = wb.to_context_text()
        assert "机器学习" in text
        assert "监督学习" in text
        assert "无监督学习" in text

    def test_to_context_text_with_summaries(self):
        wb = ResourceWhiteboard(
            topic="深度学习",
            section_summaries=["CNN: 卷积神经网络基础...", "RNN: 循环神经网络原理..."],
        )
        text = wb.to_context_text()
        assert "CNN" in text
        assert "RNN" in text
        assert "内容概述" in text

    def test_to_context_text_with_outline(self):
        wb = ResourceWhiteboard(
            topic="Python",
            outline_subsections=["变量", "函数", "类"],
        )
        text = wb.to_context_text()
        assert "变量 → 函数 → 类" in text

    def test_to_context_text_with_code_focus(self):
        wb = ResourceWhiteboard(
            topic="排序算法",
            code_focus="实现快速排序",
        )
        text = wb.to_context_text()
        assert "代码重点" in text
        assert "快速排序" in text

    def test_to_context_text_full(self):
        wb = ResourceWhiteboard(
            topic="机器学习",
            key_concepts=["监督学习", "无监督学习", "强化学习"],
            section_summaries=["监督学习: 分类与回归...", "无监督学习: 聚类与降维..."],
            outline_subsections=["监督学习", "无监督学习"],
            code_focus="实现K-means聚类",
        )
        text = wb.to_context_text()
        assert "监督学习" in text
        assert "K-means" in text
        assert "内容概述" in text
        assert "大纲结构" in text

    def test_from_content_output_basic(self):
        outline = {
            "subsections": [
                {"heading": "监督学习", "role": "core"},
                {"heading": "无监督学习", "role": "core"},
                {"heading": "实现KNN", "role": "example", "focus": "手写KNN分类器"},
            ],
        }
        content_blocks = [
            {
                "type": "section",
                "heading": "监督学习",
                "content": "监督学习是机器学习的重要分支，通过带标签的数据进行训练...",
            },
        ]
        wb = ResourceWhiteboard.from_content_output("机器学习", outline, content_blocks)
        assert wb.topic == "机器学习"
        assert "监督学习" in wb.key_concepts
        assert "无监督学习" in wb.key_concepts
        assert wb.code_focus == "手写KNN分类器"
        assert len(wb.section_summaries) == 1

    def test_from_content_output_empty(self):
        wb = ResourceWhiteboard.from_content_output("测试", {"subsections": []}, [])
        assert wb.topic == "测试"
        assert wb.key_concepts == []
        assert wb.section_summaries == []

    def test_from_content_output_max_concepts(self):
        """More than 8 subsections should cap at 8 key_concepts"""
        outline = {
            "subsections": [
                {"heading": f"概念{i}"} for i in range(12)
            ],
        }
        wb = ResourceWhiteboard.from_content_output("测试", outline, [])
        assert len(wb.key_concepts) == 8

    def test_from_content_output_code_focus_fallback(self):
        """When no role=example/application subsections, code_focus falls back to topic"""
        outline = {
            "subsections": [
                {"heading": "基础概念", "role": "core"},
            ],
        }
        wb = ResourceWhiteboard.from_content_output("机器学习", outline, [])
        assert wb.code_focus == "机器学习"
