import pytest

from app.utils.mermaid_generator import concept_graph_to_mermaid, mindmap_to_mermaid


class TestConceptGraphToMermaid:
    def test_concept_graph_to_mermaid_basic(self):
        concept_graph = {
            "nodes": [
                {"id": "A", "label": "Python"},
                {"id": "B", "label": "Variable"},
            ],
            "edges": [
                {"from": "A", "to": "B", "label": "has"},
            ],
        }
        result = concept_graph_to_mermaid(concept_graph)
        assert "graph TD" in result
        assert 'A["Python"]' in result
        assert 'B["Variable"]' in result
        assert 'A -->|"has"| B' in result

    def test_concept_graph_to_mermaid_multiple_edges(self):
        concept_graph = {
            "nodes": [
                {"id": "A", "label": "Python"},
                {"id": "B", "label": "OOP"},
                {"id": "C", "label": "Class"},
            ],
            "edges": [
                {"from": "A", "to": "B", "label": "supports"},
                {"from": "B", "to": "C", "label": "defines"},
                {"from": "A", "to": "C", "label": "uses"},
            ],
        }
        result = concept_graph_to_mermaid(concept_graph)
        assert 'A["Python"]' in result
        assert 'B["OOP"]' in result
        assert 'C["Class"]' in result
        assert 'A -->|"supports"| B' in result
        assert 'B -->|"defines"| C' in result
        assert 'A -->|"uses"| C' in result
        assert result.count("-->") == 3

    def test_concept_graph_to_mermaid_empty(self):
        concept_graph = {}
        result = concept_graph_to_mermaid(concept_graph)
        assert result == "graph TD"

    def test_concept_graph_to_mermaid_empty_lists(self):
        concept_graph = {"nodes": [], "edges": []}
        result = concept_graph_to_mermaid(concept_graph)
        assert result == "graph TD"

    def test_concept_graph_to_mermaid_node_labels_escaped(self):
        concept_graph = {
            "nodes": [
                {"id": "A", "label": 'Hello "World"'},
                {"id": "B", "label": 'Func(a,b)'},
            ],
            "edges": [
                {"from": "A", "to": "B", "label": "test"},
            ],
        }
        result = concept_graph_to_mermaid(concept_graph)
        assert "A[\"Hello 'World'\"]" in result
        assert 'B["Func(a,b)"]' in result
        assert 'Hello "World"' not in result
        assert "Func[a,b]" not in result

    def test_concept_graph_to_mermaid_edges_without_labels(self):
        concept_graph = {
            "nodes": [
                {"id": "A", "label": "A"},
                {"id": "B", "label": "B"},
            ],
            "edges": [
                {"from": "A", "to": "B"},
            ],
        }
        result = concept_graph_to_mermaid(concept_graph)
        assert "A --> B" in result


class TestMindmapToMermaid:
    def test_mindmap_to_mermaid_basic(self):
        mindmap = {
            "root": "Python",
            "children": [
                {"topic": "Syntax", "subtopics": ["Variables", "Loops"]},
                {"topic": "OOP", "subtopics": ["Classes", "Inheritance"]},
            ],
        }
        result = mindmap_to_mermaid(mindmap)
        assert "mindmap" in result
        assert 'root("Python")' in result
        assert '"Syntax"' in result
        assert '"Variables"' in result
        assert '"Loops"' in result
        assert '"OOP"' in result
        assert '"Classes"' in result
        assert '"Inheritance"' in result

    def test_mindmap_to_mermaid_nested(self):
        mindmap = {
            "root": "AI",
            "children": [
                {
                    "topic": "ML",
                    "subtopics": ["Supervised", "Unsupervised", "RL"],
                },
                {
                    "topic": "DL",
                    "subtopics": ["CNN", "RNN"],
                },
            ],
        }
        result = mindmap_to_mermaid(mindmap)
        lines = result.split("\n")
        assert lines[0] == "mindmap"
        assert "Supervised" in result
        assert "CNN" in result

    def test_mindmap_to_mermaid_empty(self):
        mindmap = {}
        result = mindmap_to_mermaid(mindmap)
        assert "mindmap" in result
        assert 'root("未命名")' in result

    def test_mindmap_to_mermaid_no_subtopics(self):
        mindmap = {
            "root": "Python",
            "children": [
                {"topic": "Syntax"},
            ],
        }
        result = mindmap_to_mermaid(mindmap)
        assert 'root("Python")' in result
        assert '"Syntax"' in result
