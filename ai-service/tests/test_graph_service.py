import pytest

from app.services.graph_service import GraphService


@pytest.fixture
def graph_service():
    service = GraphService()
    service._dynamic_graphs.clear()
    return service


class TestGraphService:
    @pytest.mark.asyncio
    async def test_get_graph_loads_skeleton(self, graph_service):
        graph = await graph_service.get_graph(course_id="ai_intro")
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) > 0
        for node in graph["nodes"]:
            assert node["type"] in {"concept", "skill", "fact"}
            assert "icon" in node
            assert "theme" in node
            assert "recommended_resource_types" in node

    @pytest.mark.asyncio
    async def test_add_node_defaults_type_and_meta(self, graph_service):
        course_id = "ai_intro"
        new = graph_service.add_node(course_id, {"id": "dynamic_node", "name": "Dynamic Node"})
        assert new["type"] == "concept"
        assert new["icon"] == "book"
        assert "theme" in new
        assert new["recommended_resource_types"] == ["video", "article", "doc"]

    @pytest.mark.asyncio
    async def test_add_node_skill_type_meta(self, graph_service):
        course_id = "ai_intro"
        new = graph_service.add_node(course_id, {"id": "dynamic_skill", "name": "Dynamic Skill", "type": "skill"})
        assert new["type"] == "skill"
        assert new["icon"] == "tools"
        assert new["recommended_resource_types"] == ["exercise", "project", "video"]

    @pytest.mark.asyncio
    async def test_add_node_unknown_type_defaults_to_concept(self, graph_service):
        course_id = "ai_intro"
        new = graph_service.add_node(course_id, {"id": "dynamic_unknown", "name": "Dynamic Unknown", "type": "algorithm"})
        assert new["type"] == "concept"

    @pytest.mark.asyncio
    async def test_get_node_card_dynamic_node_other_course(self, graph_service):
        course_id = "math_course"
        graph_service.add_node(course_id, {"id": "linear_algebra", "name": "Linear Algebra", "type": "concept"})
        card = await graph_service.get_node_card("linear_algebra", course_id=course_id)
        assert card["node"]["id"] == "linear_algebra"

    @pytest.mark.asyncio
    async def test_get_node_card_includes_type_meta(self, graph_service):
        card = await graph_service.get_node_card("ai_overview")
        node = card["node"]
        assert node["type"] == "concept"
        assert node["icon"] == "book"
        assert node["theme"]["border"] == "#2196F3"
        assert "recommended_resource_types" in node

    @pytest.mark.asyncio
    async def test_add_node_and_get_graph_merge(self, graph_service):
        course_id = "ai_intro"
        graph_service.add_node(course_id, {"id": "dynamic_node", "name": "Dynamic Node"})
        graph = await graph_service.get_graph(course_id=course_id)
        node_ids = {n["id"] for n in graph["nodes"]}
        assert "dynamic_node" in node_ids

    @pytest.mark.asyncio
    async def test_add_edge_and_get_graph_merge(self, graph_service):
        course_id = "ai_intro"
        graph_service.add_node(course_id, {"id": "src_node", "name": "Source"})
        graph_service.add_node(course_id, {"id": "tgt_node", "name": "Target"})
        graph_service.add_edge(course_id, {"source": "src_node", "target": "tgt_node", "relation": "extends"})
        graph = await graph_service.get_graph(course_id=course_id)
        edge_keys = {(e["source"], e["target"]) for e in graph["edges"]}
        assert ("src_node", "tgt_node") in edge_keys

    @pytest.mark.asyncio
    async def test_get_graph_applies_masteries(self, graph_service):
        graph = await graph_service.get_graph(course_id="ai_intro", masteries={"ai_overview": 0.9})
        for node in graph["nodes"]:
            if node["id"] == "ai_overview":
                assert node["mastery"] == 0.9
                assert node["status"] == "mastered"
                break
        else:
            pytest.fail("ai_overview node not found in skeleton")

    def test_add_edge_requires_valid_relation(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.add_edge("course", {"source": "a", "target": "b", "relation": "invalid"})

    def test_add_node_requires_identifier(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.add_node("course", {"name": ""})
