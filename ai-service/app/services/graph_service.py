"""知识图谱服务 — 骨架加载、规则补边、掌握度注入、颜色映射、节点卡片"""

import copy
import json
import logging
import os
import threading
from collections import deque
from typing import Optional

from app.services.java_api_client import get_java_client

logger = logging.getLogger(__name__)

SKELETON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "knowledge_graph_skeleton.json"
)
VALID_RELATIONS = {"depends_on", "extends", "parallel"}

STATUS_LOCKED = "locked"
STATUS_LEARNING = "learning"
STATUS_MASTERED = "mastered"
STATUS_FORGOTTEN = "forgotten"

_MOCK_SUB_CONCEPTS: dict[str, list[dict]] = {
    "ai_overview": [
        {"name": "AI 定义与图灵测试", "mastery": 0.0, "tag": "未学"},
        {"name": "AI 发展三阶段", "mastery": 0.0, "tag": "未学"},
        {"name": "ML/DL/NLP/CV 分支", "mastery": 0.0, "tag": "未学"},
    ],
    "ml_basics": [
        {"name": "监督/无监督/强化学习", "mastery": 0.0, "tag": "未学"},
        {"name": "训练集/验证集/测试集", "mastery": 0.0, "tag": "未学"},
        {"name": "偏差-方差权衡", "mastery": 0.0, "tag": "未学"},
        {"name": "特征工程基础", "mastery": 0.0, "tag": "未学"},
    ],
    "dl_basics": [
        {"name": "神经元与前向传播", "mastery": 0.0, "tag": "未学"},
        {"name": "激活函数（ReLU/Sigmoid/Tanh）", "mastery": 0.0, "tag": "未学"},
        {"name": "损失函数与优化器", "mastery": 0.0, "tag": "未学"},
        {"name": "反向传播直觉理解", "mastery": 0.0, "tag": "未学"},
    ],
    "transformer": [
        {"name": "Encoder-Decoder 结构", "mastery": 0.0, "tag": "未学"},
        {"name": "多头注意力机制", "mastery": 0.0, "tag": "未学"},
        {"name": "位置编码原理", "mastery": 0.0, "tag": "未学"},
        {"name": "残差连接与 LayerNorm", "mastery": 0.0, "tag": "未学"},
        {"name": "训练与推理流程", "mastery": 0.0, "tag": "未学"},
    ],
    "nlp_llm": [
        {"name": "语言模型演进史", "mastery": 0.0, "tag": "未学"},
        {"name": "预训练+微调范式", "mastery": 0.0, "tag": "未学"},
        {"name": "Prompt Engineering", "mastery": 0.0, "tag": "未学"},
        {"name": "LLM 能力与局限", "mastery": 0.0, "tag": "未学"},
    ],
    "backprop": [
        {"name": "链式法则矩阵形式", "mastery": 0.0, "tag": "未学"},
        {"name": "常见激活函数梯度", "mastery": 0.0, "tag": "未学"},
        {"name": "梯度消失/爆炸", "mastery": 0.0, "tag": "未学"},
        {"name": "数值稳定性技巧", "mastery": 0.0, "tag": "未学"},
    ],
    "overfitting": [
        {"name": "过拟合诊断方法", "mastery": 0.0, "tag": "未学"},
        {"name": "L1/L2 正则化", "mastery": 0.0, "tag": "未学"},
        {"name": "Dropout 与 Early Stopping", "mastery": 0.0, "tag": "未学"},
        {"name": "数据增强技术", "mastery": 0.0, "tag": "未学"},
    ],
    "self_attention": [
        {"name": "Q/K/V 线性变换", "mastery": 0.0, "tag": "未学"},
        {"name": "缩放点积注意力", "mastery": 0.0, "tag": "未学"},
        {"name": "多头并行机制", "mastery": 0.0, "tag": "未学"},
        {"name": "注意力权重可视化", "mastery": 0.0, "tag": "未学"},
    ],
    "gradient_variants": [
        {"name": "BGD/SGD/Mini-batch 区别", "mastery": 0.0, "tag": "未学"},
        {"name": "Momentum 加速", "mastery": 0.0, "tag": "未学"},
        {"name": "Adam 自适应学习率", "mastery": 0.0, "tag": "未学"},
        {"name": "学习率调度策略", "mastery": 0.0, "tag": "未学"},
    ],
    "cnn": [
        {"name": "卷积层与感受野", "mastery": 0.0, "tag": "未学"},
        {"name": "池化层与全连接层", "mastery": 0.0, "tag": "未学"},
        {"name": "LeNet/AlexNet/ResNet", "mastery": 0.0, "tag": "未学"},
        {"name": "CNN 训练技巧", "mastery": 0.0, "tag": "未学"},
    ],
}


class GraphService:
    """知识图谱服务 — 骨架加载、规则补边、掌握度注入、颜色映射"""

    def __init__(self):
        self._skeleton_cache: Optional[dict] = None
        self._client = get_java_client()

    def load_skeleton(self) -> dict:
        if self._skeleton_cache is not None:
            return self._skeleton_cache

        with open(SKELETON_PATH, "r", encoding="utf-8") as f:
            graph = json.load(f)

        self._validate_skeleton(graph)
        self._skeleton_cache = graph
        logger.info("Skeleton loaded: %d nodes, %d edges", len(graph["nodes"]), len(graph["edges"]))
        return graph

    def _validate_skeleton(self, graph: dict) -> None:
        if "nodes" not in graph or "edges" not in graph:
            raise ValueError("Skeleton JSON 缺少 nodes 或 edges 字段")

        node_ids = {n["id"] for n in graph["nodes"]}
        seen_edges = set()

        for i, edge in enumerate(graph["edges"]):
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            rel = edge.get("relation", "")

            if not src or not tgt:
                raise ValueError(f"Edge #{i} 缺少 source 或 target")
            if src not in node_ids:
                raise ValueError(f"Edge #{i} source '{src}' 不在节点列表中")
            if tgt not in node_ids:
                raise ValueError(f"Edge #{i} target '{tgt}' 不在节点列表中")
            if rel not in VALID_RELATIONS:
                raise ValueError(f"Edge #{i} relation '{rel}' 不在 {VALID_RELATIONS} 中")

            key = (src, tgt)
            if key in seen_edges:
                logger.warning("Duplicate edge: %s -> %s, skipping", src, tgt)
            seen_edges.add(key)

    @staticmethod
    def auto_add_parallel_edges(graph: dict) -> dict:
        node_ids = [n["id"] for n in graph["nodes"]]
        existing_pairs = {
            (e["source"], e["target"]) for e in graph["edges"]
        } | {(e["target"], e["source"]) for e in graph["edges"]}

        predecessors: dict[str, set[str]] = {nid: set() for nid in node_ids}
        for e in graph["edges"]:
            predecessors[e["target"]].add(e["source"])

        added = 0
        for i, n1 in enumerate(node_ids):
            for n2 in node_ids[i + 1:]:
                common = predecessors[n1] & predecessors[n2]
                if common and (n1, n2) not in existing_pairs:
                    graph["edges"].append({
                        "source": n1, "target": n2, "relation": "parallel",
                        "rationale": f"共同前置: {', '.join(sorted(common))}",
                    })
                    existing_pairs.add((n1, n2))
                    added += 1

        if added:
            logger.info("Auto-added %d parallel edges", added)
        return graph

    async def get_graph(self, user_id: int, course_id: str) -> dict:
        graph = copy.deepcopy(self.load_skeleton())
        graph = self.auto_add_parallel_edges(graph)

        masteries = await self._get_user_masteries(user_id, course_id)
        for node in graph["nodes"]:
            m = masteries.get(node["id"], 0.0)
            status = self._mastery_to_status(m)
            node["mastery"] = m
            node["status"] = status
            node["color"] = self._mastery_to_color(m, status)

        return graph

    async def get_node_card(self, user_id: int, course_id: str, node_id: str) -> dict:
        skeleton = self.load_skeleton()

        node = None
        for n in skeleton["nodes"]:
            if n["id"] == node_id:
                node = dict(n)
                break
        if node is None:
            raise ValueError(f"节点 '{node_id}' 不存在")

        masteries = await self._get_user_masteries(user_id, course_id)
        mastery = masteries.get(node_id, 0.0)
        status = self._mastery_to_status(mastery)
        node["mastery"] = mastery
        node["status"] = status
        node["color"] = self._mastery_to_color(mastery, status)

        node_map = {n["id"]: n for n in skeleton["nodes"]}
        predecessors = [e["source"] for e in skeleton["edges"] if e["target"] == node_id]
        successors = [e["target"] for e in skeleton["edges"] if e["source"] == node_id]
        related = [
            e["source"] if e["target"] == node_id else e["target"]
            for e in skeleton["edges"]
            if (e["source"] == node_id or e["target"] == node_id)
            and e["relation"] in ("parallel", "extends")
        ]

        def _context_detail(nid: str) -> dict:
            m = masteries.get(nid, 0.0)
            s = GraphService._mastery_to_status(m)
            return {
                "id": nid,
                "name": node_map.get(nid, {}).get("name", nid),
                "status": s, "mastery": m,
                "color": GraphService._mastery_to_color(m, s),
            }

        sub_concepts = _MOCK_SUB_CONCEPTS.get(node_id, [])
        node_mastery_val = masteries.get(node_id)
        if node_mastery_val is not None:
            tag = GraphService._mastery_to_tag(node_mastery_val)
            for sc in sub_concepts:
                sc["mastery"] = round(node_mastery_val, 2)
                sc["tag"] = tag

        perf = {
            "sub_concepts": sub_concepts,
            "total_exercises": await self._count_exercises(user_id),
            "last_practiced": None,
        }
        if node_mastery_val is not None:
            detail = await self._client.get_node_mastery_detail(user_id, node_id)
            if detail and detail.get("last_review_at"):
                perf["last_practiced"] = detail["last_review_at"]

        actions = self._build_actions(mastery, status)

        return {
            "node": node,
            "performance": perf,
            "graph_context": {
                "prerequisites": [_context_detail(pid) for pid in predecessors],
                "unlocks": [_context_detail(sid) for sid in successors],
                "related": [_context_detail(rid) for rid in related],
            },
            "actions": actions,
        }

    async def _count_exercises(self, user_id: int) -> int:
        try:
            return await self._client.count_exercises(user_id)
        except Exception:
            return 0

    async def _get_user_masteries(self, user_id: int, course_id: str) -> dict[str, float]:
        try:
            return await self._client.get_node_masteries(user_id, course_id)
        except Exception as e:
            logger.error("Failed to load masteries for user %d, course %s: %s", user_id, course_id, e)
            return {}

    @staticmethod
    def _mastery_to_status(mastery: float) -> str:
        if mastery <= 0.0:
            return STATUS_LOCKED
        elif mastery < 0.85:
            return STATUS_LEARNING
        else:
            return STATUS_MASTERED

    @staticmethod
    def _mastery_to_color(mastery: float, status: str) -> dict:
        if status == STATUS_FORGOTTEN:
            return {"bg": "#F5E6D6", "border": "#E07A3A", "label": "需要复习"}
        if mastery <= 0.0:
            return {"bg": "#E8E8ED", "border": "#C4C4CC", "label": "未开始"}
        elif mastery < 0.3:
            return {"bg": "#F2E8D9", "border": "#D4A96A", "label": "初步接触"}
        elif mastery < 0.6:
            return {"bg": "#D6E8F0", "border": "#6AA3C4", "label": "学习中"}
        elif mastery < 0.85:
            return {"bg": "#D6EDD9", "border": "#6AB87A", "label": "基本掌握"}
        else:
            return {"bg": "#C8DFF5", "border": "#4A8EC4", "label": "熟练掌握"}

    @staticmethod
    def _build_actions(mastery: float, status: str) -> list[dict]:
        actions = []
        if status == STATUS_LOCKED:
            actions.append({"label": "开始学习", "type": "primary", "target": "resource"})
        elif status == STATUS_FORGOTTEN:
            actions.append({"label": "重新复习", "type": "warning", "target": "review"})
        else:
            actions.append({"label": "继续学习", "type": "primary", "target": "resource"})
            actions.append({"label": "做练习题", "type": "secondary", "target": "exercise"})
            if mastery >= 0.3:
                actions.append({"label": "查看复习提醒", "type": "warning", "target": "review"})
        return actions

    # ── 图谱算法 ────────────────────────────────────

    def get_successors(self, node_id: str) -> list[str]:
        skeleton = self.load_skeleton()
        return [e["target"] for e in skeleton["edges"] if e["source"] == node_id]

    def get_predecessors(self, node_id: str) -> list[str]:
        skeleton = self.load_skeleton()
        return [e["source"] for e in skeleton["edges"] if e["target"] == node_id]

    def topological_sort(self) -> list[str]:
        skeleton = self.load_skeleton()
        nodes = {n["id"] for n in skeleton["nodes"]}
        edges = skeleton["edges"]

        in_degree = {nid: 0 for nid in nodes}
        adj = {nid: [] for nid in nodes}
        for e in edges:
            src, tgt = e["source"], e["target"]
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)
                in_degree[tgt] += 1

        queue = deque([nid for nid in nodes if in_degree[nid] == 0])
        result = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(nodes):
            logger.warning("Graph has cycles, falling back to original order")
            return [n["id"] for n in skeleton["nodes"]]

        return result

    def get_critical_path(self, start_node: str, end_node: str) -> list[str]:
        skeleton = self.load_skeleton()
        nodes = {n["id"] for n in skeleton["nodes"]}
        if start_node not in nodes or end_node not in nodes:
            return []

        edges = skeleton["edges"]
        adj = {nid: [] for nid in nodes}
        for e in edges:
            src, tgt = e["source"], e["target"]
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)

        topo = self.topological_sort()
        dist = {nid: float("-inf") for nid in nodes}
        parent = {nid: None for nid in nodes}
        dist[start_node] = 0

        for u in topo:
            if dist[u] == float("-inf"):
                continue
            for v in adj[u]:
                if dist[v] < dist[u] + 1:
                    dist[v] = dist[u] + 1
                    parent[v] = u

        if dist[end_node] == float("-inf"):
            return []

        path = []
        cur = end_node
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        return path

    @staticmethod
    def _mastery_to_tag(mastery: float) -> str:
        if mastery <= 0.0:
            return "未学"
        elif mastery < 0.3:
            return "初学"
        elif mastery < 0.6:
            return "学习中"
        elif mastery < 0.85:
            return "基本掌握"
        else:
            return "已掌握"


_graph_service: Optional[GraphService] = None
_graph_service_lock = threading.Lock()


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        with _graph_service_lock:
            if _graph_service is None:
                _graph_service = GraphService()
    return _graph_service
