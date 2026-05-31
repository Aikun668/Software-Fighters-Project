"""MindMapAgent — 思维导图生成智能体

生成层级化思维导图节点（markmap 兼容 JSON）+ Mermaid 概念关系图。
支持 LLM 生成 + 静态 fallback 双路径。
"""

import json
import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.utils.mermaid_generator import concept_graph_to_mermaid
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)


class MindMapState(TypedDict, total=False):
    topic: str
    student_profile: dict
    outline: dict
    whiteboard_context: str
    peer_context: str
    blocks: list[dict]
    response: str


class MindMapAgent(BaseAgent):
    """思维导图生成 Agent — 输出 mindmap + mermaid 两类 block"""

    def __init__(self, config=None, use_mock_llm: bool = True,
                 model_profile=None):
        super().__init__(
            agent_name="mindmap_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(MindMapState)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("generate")
        graph.set_finish_point("generate")
        return graph.compile()

    @staticmethod
    def _validate_nodes(result: dict) -> list[str]:
        """验证 nodes 字段的结构完整性"""
        issues = []
        nodes = result.get("nodes", [])
        if not isinstance(nodes, list) or len(nodes) == 0:
            issues.append("nodes 必须是非空数组")
            return issues
        for i, node in enumerate(nodes):
            if not isinstance(node.get("id"), str) or not node["id"]:
                issues.append(f"nodes[{i}] 缺少或 id 为空")
            if not isinstance(node.get("label"), str) or not node["label"]:
                issues.append(f"nodes[{i}] 缺少或 label 为空")
        return issues

    async def _generate_node(self, state: MindMapState) -> dict:
        topic = state.get("topic", "")
        outline = state.get("outline", {})
        student_profile = state.get("student_profile", {})
        whiteboard_context = state.get("whiteboard_context", "")
        peer_context = state.get("peer_context", "")

        subsections = outline.get("subsections", [])
        subsection_labels = [sub.get("heading", f"第{i+1}节") for i, sub in enumerate(subsections)]

        # ── LLM 路径：调用 LLM 生成层级化思维导图 ──
        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "topic_summary": outline.get("intro", f"关于{topic}的知识体系"),
                "objectives": f"构建{topic}的完整知识结构思维导图",
                "outline_subsections": json.dumps(subsection_labels, ensure_ascii=False),
                "student_profile": self._format_profile(student_profile),
                "whiteboard_context": whiteboard_context,
                "peer_context": peer_context,
            },
        )

        result = await self._call_llm_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            expected_key="nodes",
            fallback={},
            validator=self._validate_nodes,
        )
        nodes = result.get("nodes", [])

        # ── Fallback：从 outline 静态构建 ──
        if not nodes:
            nodes = self._build_fallback_nodes(topic, subsections)

        # ── 构建 mindmap block ──
        mindmap_json = json.dumps({"nodes": nodes}, ensure_ascii=False)
        blocks = [{"type": "mindmap", "heading": "知识结构", "content": mindmap_json}]

        # ── 构建 Mermaid 概念图 ──
        mermaid_input = self._nodes_to_concept_graph(topic, nodes)
        try:
            mermaid_diagram = concept_graph_to_mermaid(mermaid_input)
        except Exception:
            mermaid_diagram = f"graph TD\n  root[\"{topic}\"]"

        blocks.append({
            "type": "mermaid", "heading": "概念关系图",
            "content": mermaid_diagram,
        })

        logger.info(f"MindMapAgent generated {len(nodes)} nodes for topic '{topic}'")
        return {"blocks": blocks, "response": f"已生成「{topic}」的思维导图，包含 {len(nodes)} 个节点。"}

    def _build_fallback_nodes(self, topic: str, subsections: list[dict]) -> list[dict]:
        """从大纲静态构建层级化节点（fallback 路径）"""
        root_children = []
        for i, sub in enumerate(subsections):
            heading = sub.get("heading", f"第{i+1}节")
            focus = sub.get("focus", heading)
            child_id = f"sub-{i}"
            root_children.append({
                "id": child_id,
                "label": heading,
                "children": [
                    {"id": f"{child_id}-concept", "label": "核心概念"},
                    {"id": f"{child_id}-principle", "label": "基本原理"},
                    {"id": f"{child_id}-apply", "label": "实践应用"},
                ],
            })
        return [{"id": "root", "label": topic, "children": root_children}]

    def _nodes_to_concept_graph(self, topic: str, nodes: list[dict]) -> dict:
        """将层级化节点转为 concept_graph_to_mermaid 的输入格式"""
        graph_nodes = []
        graph_edges = []

        def _walk(node_list, parent_id=None):
            for n in node_list:
                nid = n.get("id", "")
                graph_nodes.append({"id": nid, "label": n.get("label", nid)})
                if parent_id:
                    graph_edges.append({"from": parent_id, "to": nid, "label": ""})
                children = n.get("children", [])
                if children:
                    _walk(children, nid)

        _walk(nodes)
        return {"nodes": graph_nodes, "edges": graph_edges}
