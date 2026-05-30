"""Convert concept graphs and mindmaps to Mermaid diagram syntax.
Pattern borrowed from DeepTutor's Mermaid concept graph rendering."""

import logging

logger = logging.getLogger(__name__)


def concept_graph_to_mermaid(concept_graph: dict) -> str:
    """Convert {nodes: [{id, label}], edges: [{from, to, label}]} to Mermaid graph TD syntax."""
    nodes = concept_graph.get("nodes", [])
    edges = concept_graph.get("edges", [])

    lines = ["graph TD"]

    for node in nodes:
        node_id = str(node.get("id", "?")).replace(" ", "_")
        label = node.get("label", node_id)
        label = label.replace('"', "'")
        lines.append(f'  {node_id}["{label}"]')

    for edge in edges:
        from_node = edge.get("from", "?")
        to_node = edge.get("to", "?")
        label = edge.get("label", "")
        if label:
            lines.append(f'  {from_node} -->|"{label}"| {to_node}')
        else:
            lines.append(f'  {from_node} --> {to_node}')

    return "\n".join(lines)


def mindmap_to_mermaid(mindmap: dict) -> str:
    """Convert {root, children: [{topic, subtopics: [...]}]} to Mermaid mindmap syntax."""
    root = mindmap.get("root", "未命名")
    children = mindmap.get("children", [])

    lines = ["mindmap"]
    lines.append(f'  root("{root}")')

    for child in children:
        topic = child.get("topic", "")
        subtopics = child.get("subtopics", [])
        if topic:
            lines.append(f'    "{topic}"')
            for sub in subtopics:
                if sub:
                    lines.append(f'      "{sub}"')
        else:
            for sub in subtopics:
                if sub:
                    lines.append(f'    "{sub}"')

    return "\n".join(lines)
