"""Tests for MindMapAgent — 思维导图生成智能体"""

import json
import pytest

from app.agents.mindmap_agent import MindMapAgent


class TestMindMapAgent:
    @pytest.fixture
    def agent(self):
        return MindMapAgent()

    def test_agent_instantiation(self):
        agent = MindMapAgent()
        assert agent.agent_name == "mindmap_agent"
        assert agent._compiled_graph is not None

    @pytest.mark.asyncio
    async def test_generate_node_with_outline(self, agent):
        outline = {
            "intro": "机器学习是人工智能的核心分支",
            "subsections": [
                {"heading": "监督学习", "role": "core", "focus": "分类与回归"},
                {"heading": "无监督学习", "role": "core", "focus": "聚类与降维"},
            ],
        }
        state = {
            "topic": "机器学习",
            "student_profile": {"knowledge_base": 60},
            "outline": outline,
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        mindmap_blocks = [b for b in blocks if b["type"] == "mindmap"]
        assert len(mindmap_blocks) >= 1

    @pytest.mark.asyncio
    async def test_generate_node_mermaid_block(self, agent):
        state = {
            "topic": "深度学习",
            "student_profile": {},
            "outline": {"subsections": [{"heading": "CNN", "role": "core", "focus": "卷积"}]},
        }
        result = await agent._generate_node(state)
        blocks = result.get("blocks", [])
        mermaid_blocks = [b for b in blocks if b["type"] == "mermaid"]
        assert len(mermaid_blocks) >= 1

    def test_build_fallback_nodes(self, agent):
        subsections = [
            {"heading": "基础概念", "role": "core"},
            {"heading": "核心原理", "role": "core"},
        ]
        nodes = agent._build_fallback_nodes("测试主题", subsections)
        assert len(nodes) == 1
        assert nodes[0]["id"] == "root"
        assert nodes[0]["label"] == "测试主题"
        children = nodes[0].get("children", [])
        assert len(children) == 2

    def test_nodes_to_concept_graph(self, agent):
        nodes = [
            {
                "id": "root",
                "label": "AI",
                "children": [
                    {"id": "ml", "label": "机器学习", "children": []},
                ],
            }
        ]
        graph = agent._nodes_to_concept_graph("AI", nodes)
        assert "nodes" in graph
        assert "edges" in graph
        assert any(n["id"] == "root" for n in graph["nodes"])
        assert any(n["id"] == "ml" for n in graph["nodes"])
        assert any(e["from"] == "root" and e["to"] == "ml" for e in graph["edges"])

    @pytest.mark.asyncio
    async def test_run_integration(self, agent):
        state = {
            "topic": "Python基础",
            "student_profile": {"knowledge_base": 30, "cognitive_style": "visual"},
            "outline": {
                "intro": "Python基础知识",
                "subsections": [
                    {"heading": "变量与类型", "role": "core"},
                    {"heading": "控制流", "role": "core"},
                ],
            },
        }
        result = await agent.run(state)
        blocks = result.get("blocks", [])
        assert len(blocks) >= 1
        types = {b["type"] for b in blocks}
        assert "mindmap" in types
