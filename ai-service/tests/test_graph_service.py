import pytest

from app.services.graph_service import GraphService, VALID_RELATIONS


@pytest.fixture
def graph_service():
    service = GraphService()
    return service


class TestGraphService:
    # ── get_graph ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_graph_loads_skeleton(self, graph_service):
        graph = await graph_service.get_graph()
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) == 10
        assert len(graph["edges"]) >= 13
        for node in graph["nodes"]:
            assert "id" in node
            assert "name" in node
            assert "type" in node
            assert "difficulty" in node
            assert "mastery" in node
            assert "status" in node
            assert "color" in node
            assert node["type"] in {"concept", "skill"}

    @pytest.mark.asyncio
    async def test_get_graph_applies_masteries(self, graph_service):
        graph = await graph_service.get_graph(masteries={"ai_overview": 0.9})
        for node in graph["nodes"]:
            if node["id"] == "ai_overview":
                assert node["mastery"] == 0.9
                assert node["status"] == "mastered"
                break
        else:
            pytest.fail("ai_overview node not found")

    @pytest.mark.asyncio
    async def test_get_graph_accepts_course_id(self, graph_service):
        graph = await graph_service.get_graph(course_id="ai_intro")
        assert len(graph["nodes"]) == 10

    # ── get_node_card ────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_node_card_returns_full_detail(self, graph_service):
        card = await graph_service.get_node_card("ai_overview")
        assert card["node"]["id"] == "ai_overview"
        assert "mastery" in card["node"]
        assert "status" in card["node"]
        assert "color" in card["node"]
        assert "graph_context" in card
        assert "prerequisites" in card["graph_context"]
        assert "unlocks" in card["graph_context"]
        assert "actions" in card
        assert "performance" in card

    @pytest.mark.asyncio
    async def test_get_node_card_unknown_node_raises(self, graph_service):
        with pytest.raises(ValueError):
            await graph_service.get_node_card("nonexistent_node")

    # ── add_node ─────────────────────────────────────

    def test_add_node_basic(self, graph_service):
        new = graph_service.add_node("ai_intro", {"id": "test_node", "name": "Test"})
        assert new["id"] == "test_node"
        assert new["type"] == "concept"
        assert new["difficulty"] == 3
        assert new["category"] == "其他"

    def test_add_node_custom_fields(self, graph_service):
        new = graph_service.add_node("ai_intro", {
            "id": "skill_node", "name": "Skill", "type": "skill",
            "difficulty": 5, "category": "ML",
        })
        assert new["type"] == "skill"
        assert new["difficulty"] == 5
        assert new["category"] == "ML"

    def test_add_node_duplicate_raises(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "dup"})
        with pytest.raises(ValueError):
            graph_service.add_node("ai_intro", {"id": "dup"})

    def test_add_node_no_id_raises(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.add_node("ai_intro", {"name": "no_id"})

    def test_add_node_difficulty_clamped(self, graph_service):
        new = graph_service.add_node("ai_intro", {"id": "clamp_test", "difficulty": 99})
        assert new["difficulty"] == 5

    # ── add_edge ─────────────────────────────────────

    def test_add_edge_valid(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "a"})
        graph_service.add_node("ai_intro", {"id": "b"})
        edge = graph_service.add_edge("ai_intro", {
            "source": "a", "target": "b", "relation": "extends",
        })
        assert edge["source"] == "a"
        assert edge["target"] == "b"
        assert edge["relation"] == "extends"

    def test_add_edge_invalid_relation_raises(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "a"})
        graph_service.add_node("ai_intro", {"id": "b"})
        with pytest.raises(ValueError):
            graph_service.add_edge("ai_intro", {
                "source": "a", "target": "b", "relation": "invalid",
            })

    def test_add_edge_missing_source_raises(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.add_edge("ai_intro", {"target": "x"})

    def test_add_edge_nonexistent_node_raises(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "a"})
        with pytest.raises(ValueError):
            graph_service.add_edge("ai_intro", {"source": "a", "target": "ghost"})

    def test_add_edge_duplicate_raises(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "a"})
        graph_service.add_node("ai_intro", {"id": "b"})
        graph_service.add_edge("ai_intro", {"source": "a", "target": "b"})
        with pytest.raises(ValueError):
            graph_service.add_edge("ai_intro", {"source": "a", "target": "b"})

    # ── delete_node ──────────────────────────────────

    def test_delete_dynamic_node(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "temp"})
        deleted = graph_service.delete_node("ai_intro", "temp")
        assert deleted["id"] == "temp"
        with pytest.raises(ValueError):
            graph_service.delete_node("ai_intro", "temp")

    def test_delete_skeleton_node_raises(self, graph_service):
        with pytest.raises(ValueError, match="骨架节点"):
            graph_service.delete_node("ai_intro", "ai_overview")

    def test_delete_cascades_edges(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "temp_a"})
        graph_service.add_node("ai_intro", {"id": "temp_b"})
        graph_service.add_edge("ai_intro", {"source": "temp_a", "target": "temp_b"})
        graph_service.delete_node("ai_intro", "temp_a")
        skeleton = graph_service.load_skeleton()
        remaining = {(e["source"], e["target"]) for e in skeleton["edges"]}
        assert ("temp_a", "temp_b") not in remaining

    # ── update_node ──────────────────────────────────

    def test_update_skeleton_node_allowed_fields(self, graph_service):
        updated = graph_service.update_node("ai_intro", "ai_overview", {"difficulty": 4})
        assert updated["difficulty"] == 4

    def test_update_skeleton_node_rejects_other_fields(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.update_node("ai_intro", "ai_overview", {"name": "Hacked"})

    def test_update_dynamic_node_all_fields(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "dyn"})
        updated = graph_service.update_node("ai_intro", "dyn", {"name": "Renamed"})
        assert updated["name"] == "Renamed"

    # ── check_prerequisites ──────────────────────────

    def test_check_prerequisites_all_met(self, graph_service):
        result = graph_service.check_prerequisites(
            "ml_basics",
            masteries={"ai_overview": 0.9},
            threshold=0.6,
        )
        assert result["can_learn"] is True
        assert result["met_count"] == result["total_prerequisites"]

    def test_check_prerequisites_some_unmet(self, graph_service):
        result = graph_service.check_prerequisites(
            "dl_basics",
            masteries={"ai_overview": 0.9, "ml_basics": 0.3},
            threshold=0.6,
        )
        assert result["can_learn"] is False
        assert result["unmet_count"] > 0
        assert len(result["unmet"]) > 0

    def test_check_prerequisites_no_prerequisites(self, graph_service):
        result = graph_service.check_prerequisites(
            "ai_overview",
            masteries={},
            threshold=0.6,
        )
        assert result["can_learn"] is True
        assert result["total_prerequisites"] == 0

    def test_check_prerequisites_unknown_node_raises(self, graph_service):
        with pytest.raises(ValueError):
            graph_service.check_prerequisites("ghost", {}, 0.6)

    # ── get_layered_graph ────────────────────────────

    @pytest.mark.asyncio
    async def test_get_layered_graph_has_layers(self, graph_service):
        graph = graph_service.get_layered_graph()
        assert "nodes" in graph
        assert "layers" in graph
        assert "max_layer" in graph
        assert graph["max_layer"] >= 0
        for node in graph["nodes"]:
            assert "layer" in node

    @pytest.mark.asyncio
    async def test_get_layered_graph_root_nodes_layer_zero(self, graph_service):
        graph = graph_service.get_layered_graph()
        root_ids = {n["id"] for n in graph["nodes"] if n.get("layer") == 0}
        assert "ai_overview" in root_ids

    # ── recommend_next_node ──────────────────────────

    def test_recommend_returns_candidates(self, graph_service):
        candidates = graph_service.recommend_next_node({})
        assert isinstance(candidates, list)
        assert len(candidates) > 0
        for c in candidates:
            assert "node_id" in c
            assert "readiness" in c
            assert "unmet_prerequisites" in c

    def test_recommend_root_nodes_first(self, graph_service):
        candidates = graph_service.recommend_next_node({})
        first = candidates[0]
        assert first["unmet_prerequisites"] == []

    def test_recommend_excludes_mastered(self, graph_service):
        candidates = graph_service.recommend_next_node(
            {"ai_overview": 0.95, "ml_basics": 0.9, "dl_basics": 0.9,
             "transformer": 0.9, "nlp_llm": 0.9, "backprop": 0.9,
             "overfitting": 0.9, "self_attention": 0.9,
             "gradient_variants": 0.9, "cnn": 0.9}
        )
        assert len(candidates) == 0

    # ── get_progress_summary ─────────────────────────

    def test_progress_summary_counts(self, graph_service):
        summary = graph_service.get_progress_summary(
            {"ai_overview": 0.95, "ml_basics": 0.5}
        )
        assert summary["total_nodes"] == 10
        assert summary["mastered_count"] + summary["learning_count"] + summary["locked_count"] == 10
        assert "by_category" in summary
        assert "by_difficulty" in summary
        assert "recommended_focus" in summary

    def test_progress_summary_empty(self, graph_service):
        summary = graph_service.get_progress_summary({})
        assert summary["total_nodes"] == 10
        assert summary["global_mastery_pct"] == 0.0

    # ── export_mermaid ───────────────────────────────

    def test_export_mermaid_has_keywords(self, graph_service):
        mermaid = graph_service.export_mermaid()
        assert "flowchart TD" in mermaid
        assert "ai_overview" in mermaid
        assert "-->" in mermaid

    def test_export_mermaid_with_masteries(self, graph_service):
        mermaid = graph_service.export_mermaid(masteries={"ai_overview": 0.95})
        assert "已掌握" in mermaid

    # ── suggest_edges ────────────────────────────────

    @pytest.mark.real_llm
    @pytest.mark.asyncio
    async def test_suggest_edges_returns_list(self, graph_service):
        suggestions = await graph_service.suggest_edges()
        assert isinstance(suggestions, list)

    # ── load_skeleton ────────────────────────────────

    def test_force_reload(self, graph_service):
        first = graph_service.load_skeleton()
        graph_service.add_node("ai_intro", {"id": "force_test"})
        reloaded = graph_service.load_skeleton(force_reload=True)
        ids = {n["id"] for n in reloaded["nodes"]}
        assert "force_test" not in ids

    # ── _all_nodes ───────────────────────────────────

    def test_all_nodes_includes_dynamic(self, graph_service):
        graph_service.add_node("ai_intro", {"id": "dyn_all"})
        all_ids = {n["id"] for n in graph_service._all_nodes()}
        assert "dyn_all" in all_ids
        assert "ai_overview" in all_ids
