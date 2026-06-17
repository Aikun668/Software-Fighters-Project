"""知识图谱服务 — 骨架加载、规则补边、掌握度注入、颜色映射、节点卡片"""

import copy
import json
import logging
import os
import threading
from collections import deque
from typing import Optional

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
        self._original_skeleton_node_ids: set[str] = set()

    def load_skeleton(self, force_reload: bool = False) -> dict:
        if force_reload:
            self._skeleton_cache = None
            self._original_skeleton_node_ids = set()
        if self._skeleton_cache is not None:
            return self._skeleton_cache

        with open(SKELETON_PATH, "r", encoding="utf-8") as f:
            graph = json.load(f)

        self._validate_skeleton(graph)
        self._original_skeleton_node_ids = {n["id"] for n in graph["nodes"]}
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

    async def get_graph(self, course_id: str | None = None,
                       masteries: dict[str, float] | None = None) -> dict:
        graph = copy.deepcopy(self.load_skeleton())
        graph = self.auto_add_parallel_edges(graph)

        masteries = masteries or {}
        for node in graph["nodes"]:
            m = masteries.get(node["id"], 0.0)
            status = self._mastery_to_status(m)
            node["mastery"] = m
            node["status"] = status
            node["color"] = self._mastery_to_color(m, status)

        return graph

    async def get_node_card(self, node_id: str,
                            course_id: str | None = None,
                            masteries: dict[str, float] | None = None,
                            total_exercises: int = 0,
                            last_practiced: str | None = None) -> dict:
        skeleton = self.load_skeleton()

        node = None
        for n in skeleton["nodes"]:
            if n["id"] == node_id:
                node = dict(n)
                break
        if node is None:
            raise ValueError(f"节点 '{node_id}' 不存在")

        masteries = masteries or {}
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
            "total_exercises": total_exercises,
            "last_practiced": last_practiced,
        }

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

    # ── 图谱维护 CRUD ────────────────────────────────

    def _all_nodes(self, course_id: str | None = None) -> list[dict]:
        """返回当前图谱所有节点（骨架 + 动态添加）。"""
        skeleton = self.load_skeleton()
        return skeleton["nodes"]

    def add_node(self, course_id: str, data: dict) -> dict:
        """添加动态节点到图谱。"""
        skeleton = self.load_skeleton()
        node_id = data.get("id", "")
        if not node_id:
            raise ValueError("节点 id 不能为空")
        for n in skeleton["nodes"]:
            if n["id"] == node_id:
                raise ValueError(f"节点 '{node_id}' 已存在")
        node = {
            "id": node_id,
            "name": data.get("name", node_id),
            "type": data.get("type", "concept"),
            "description": data.get("description", ""),
            "difficulty": max(1, min(5, int(data.get("difficulty", 3)))),
            "category": data.get("category", "其他"),
        }
        skeleton["nodes"].append(node)
        return node

    def add_edge(self, course_id: str, data: dict) -> dict:
        """添加边到图谱。"""
        skeleton = self.load_skeleton()
        src = data.get("source", "")
        tgt = data.get("target", "")
        rel = data.get("relation", "depends_on")
        if not src or not tgt:
            raise ValueError("边的 source 和 target 不能为空")
        node_ids = {n["id"] for n in skeleton["nodes"]}
        if src not in node_ids:
            raise ValueError(f"source 节点 '{src}' 不存在")
        if tgt not in node_ids:
            raise ValueError(f"target 节点 '{tgt}' 不存在")
        if rel not in VALID_RELATIONS:
            raise ValueError(f"relation '{rel}' 不在 {VALID_RELATIONS} 中")
        for e in skeleton["edges"]:
            if e["source"] == src and e["target"] == tgt:
                raise ValueError(f"边 {src} -> {tgt} 已存在")
        edge = {
            "source": src, "target": tgt, "relation": rel,
            "rationale": data.get("rationale", ""),
        }
        skeleton["edges"].append(edge)
        return edge

    def delete_node(self, course_id: str, node_id: str) -> dict:
        """删除节点（骨架节点不可删，动态节点可删并级联删除关联边）。"""
        skeleton = self.load_skeleton()
        if node_id in self._original_skeleton_node_ids:
            raise ValueError("骨架节点不可删除")
        target = None
        for i, n in enumerate(skeleton["nodes"]):
            if n["id"] == node_id:
                target = skeleton["nodes"].pop(i)
                break
        if target is None:
            raise ValueError(f"节点 '{node_id}' 不存在")
        skeleton["edges"] = [
            e for e in skeleton["edges"]
            if e["source"] != node_id and e["target"] != node_id
        ]
        return target

    def update_node(self, course_id: str, node_id: str, updates: dict) -> dict:
        """更新节点元数据。骨架节点仅可改 difficulty/category，动态节点全字段可改。"""
        skeleton = self.load_skeleton()
        target = None
        for n in skeleton["nodes"]:
            if n["id"] == node_id:
                target = n
                break
        if target is None:
            raise ValueError(f"节点 '{node_id}' 不存在")
        is_skeleton = node_id in self._original_skeleton_node_ids

        allowed = {"difficulty", "category"} if is_skeleton else {
            "name", "description", "difficulty", "category", "type",
        }
        for key, value in updates.items():
            if key not in allowed:
                raise ValueError(
                    f"节点 '{node_id}' 不允许修改字段 '{key}'"
                    + ("（骨架节点仅可改 difficulty/category）" if is_skeleton else "")
                )
            if key == "difficulty":
                target[key] = max(1, min(5, int(value)))
            else:
                target[key] = value
        return target

    # ── 图谱分析 ──────────────────────────────────────

    def check_prerequisites(self, node_id: str,
                            masteries: dict[str, float],
                            threshold: float,
                            course_id: str | None = None) -> dict:
        """检查用户是否满足学习指定节点的前置条件。"""
        skeleton = self.load_skeleton()
        node_map = {n["id"]: n for n in skeleton["nodes"]}
        if node_id not in node_map:
            raise ValueError(f"节点 '{node_id}' 不存在")

        pred_ids = [
            e["source"] for e in skeleton["edges"]
            if e["target"] == node_id and e["relation"] == "depends_on"
        ]

        prereqs = []
        for pid in pred_ids:
            m = masteries.get(pid, 0.0)
            met = m >= threshold
            prereqs.append({
                "node_id": pid,
                "name": node_map.get(pid, {}).get("name", pid),
                "mastery": m,
                "met": met,
                "gap": round(max(0.0, threshold - m), 2) if not met else 0.0,
            })

        met_count = sum(1 for p in prereqs if p["met"])
        return {
            "node_id": node_id,
            "node_name": node_map[node_id].get("name", node_id),
            "can_learn": met_count == len(prereqs),
            "prerequisites": prereqs,
            "unmet": [p for p in prereqs if not p["met"]],
            "met_count": met_count,
            "unmet_count": len(prereqs) - met_count,
            "total_prerequisites": len(prereqs),
            "threshold": threshold,
        }

    def get_layered_graph(self,
                          masteries: dict[str, float] | None = None,
                          course_id: str | None = None) -> dict:
        """返回带层级信息的图谱（供前端分层布局）。"""
        skeleton = copy.deepcopy(self.load_skeleton())
        skeleton = self.auto_add_parallel_edges(skeleton)

        masteries = masteries or {}
        node_map = {n["id"]: n for n in skeleton["nodes"]}
        for node in skeleton["nodes"]:
            m = masteries.get(node["id"], 0.0)
            status = self._mastery_to_status(m)
            node["mastery"] = m
            node["status"] = status
            node["color"] = self._mastery_to_color(m, status)

        # BFS 分层：仅考虑 depends_on 边
        in_degree = {n["id"]: 0 for n in skeleton["nodes"]}
        adj = {n["id"]: [] for n in skeleton["nodes"]}
        for e in skeleton["edges"]:
            if e["relation"] == "depends_on":
                adj[e["source"]].append(e["target"])
                in_degree[e["target"]] += 1

        layer = {nid: 0 for nid in in_degree}
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                layer[v] = max(layer[v], layer[u] + 1)
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        unlayered = [nid for nid, deg in in_degree.items() if deg > 0]
        if unlayered:
            logger.warning("Graph has cycle in depends_on edges, using topological fallback")
            topo = self.topological_sort()
            for i, nid in enumerate(topo):
                layer[nid] = i

        for node in skeleton["nodes"]:
            node["layer"] = layer.get(node["id"], 0)

        max_layer = max(layer.values()) if layer else 0
        layer_groups: dict[int, list[str]] = {}
        for nid, l in layer.items():
            layer_groups.setdefault(l, []).append(nid)

        layers = [
            {"layer": l, "nodes": sorted(node_ids)}
            for l, node_ids in sorted(layer_groups.items())
        ]

        return {
            "nodes": skeleton["nodes"],
            "edges": skeleton["edges"],
            "layers": layers,
            "max_layer": max_layer,
        }

    def recommend_next_node(self,
                            masteries: dict[str, float],
                            course_id: str | None = None) -> list[dict]:
        """根据当前掌握度推荐下一个该学的节点。"""
        skeleton = self.load_skeleton()
        node_map = {n["id"]: n for n in skeleton["nodes"]}

        prereqs: dict[str, list[str]] = {n["id"]: [] for n in skeleton["nodes"]}
        for e in skeleton["edges"]:
            if e["relation"] == "depends_on":
                prereqs[e["target"]].append(e["source"])

        successors: dict[str, int] = {}
        for n in skeleton["nodes"]:
            successors[n["id"]] = sum(
                1 for e in skeleton["edges"]
                if e["source"] == n["id"] and e["relation"] == "depends_on"
            )

        candidates = []
        for node in skeleton["nodes"]:
            nid = node["id"]
            m = masteries.get(nid, 0.0)
            if m >= 0.85:
                continue
            pred_list = prereqs[nid]
            if pred_list:
                readiness = sum(masteries.get(p, 0.0) for p in pred_list) / len(pred_list)
                unmet = [p for p in pred_list if masteries.get(p, 0.0) < 0.85]
            else:
                readiness = 1.0
                unmet = []
            candidates.append({
                "node_id": nid,
                "name": node.get("name", nid),
                "mastery": m,
                "status": self._mastery_to_status(m),
                "difficulty": node.get("difficulty", 1),
                "category": node.get("category", ""),
                "readiness": round(readiness, 4),
                "unmet_prerequisites": unmet,
                "unlocks_count": successors.get(nid, 0),
            })

        candidates.sort(key=lambda c: (
            len(c["unmet_prerequisites"]),
            -c["readiness"],
            c["difficulty"],
        ))
        return candidates[:10]

    def get_progress_summary(self,
                             masteries: dict[str, float],
                             course_id: str | None = None) -> dict:
        """学习进度概要：全局掌握率 + 各分类/难度统计。"""
        skeleton = self.load_skeleton()
        nodes = skeleton["nodes"]

        total = len(nodes)
        if total == 0:
            return {
                "total_nodes": 0, "mastered_count": 0, "learning_count": 0,
                "locked_count": 0, "global_mastery_pct": 0.0,
                "by_category": {}, "by_difficulty": {}, "recommended_focus": [],
            }

        by_cat: dict[str, dict] = {}
        by_diff: dict[int, dict] = {}
        all_mastery = []

        for node in nodes:
            nid = node["id"]
            m = masteries.get(nid, 0.0)
            status = self._mastery_to_status(m)
            cat = node.get("category", "未分类")
            diff = node.get("difficulty", 1)
            all_mastery.append(m)

            for bucket, key in [(by_cat, cat), (by_diff, diff)]:
                if key not in bucket:
                    bucket[key] = {"total": 0, "mastered": 0, "learning": 0,
                                   "locked": 0, "mastery_sum": 0.0}
                bucket[key]["total"] += 1
                bucket[key][status] += 1
                bucket[key]["mastery_sum"] += m

        mastered_count = sum(1 for n in nodes
                             if self._mastery_to_status(masteries.get(n["id"], 0.0)) == STATUS_MASTERED)
        learning_count = sum(1 for n in nodes
                             if self._mastery_to_status(masteries.get(n["id"], 0.0)) == STATUS_LEARNING)
        locked_count = total - mastered_count - learning_count
        global_pct = round(sum(all_mastery) / total * 100, 1)

        for bucket in (by_cat, by_diff):
            for k, v in bucket.items():
                v["avg_mastery"] = round(v["mastery_sum"] / max(v["total"], 1), 2)
                v.pop("mastery_sum", None)

        cat_avg = {
            cat: data["avg_mastery"]
            for cat, data in by_cat.items()
        }
        recommended_focus = sorted(cat_avg, key=cat_avg.get)[:2]

        return {
            "total_nodes": total,
            "mastered_count": mastered_count,
            "learning_count": learning_count,
            "locked_count": locked_count,
            "global_mastery_pct": global_pct,
            "by_category": by_cat,
            "by_difficulty": {int(k): v for k, v in sorted(by_diff.items())},
            "recommended_focus": recommended_focus,
        }

    # ── 可视化导出 ────────────────────────────────────

    def export_mermaid(self,
                       course_id: str | None = None,
                       masteries: dict[str, float] | None = None) -> str:
        """导出知识图谱为 Mermaid flowchart 语法。"""
        skeleton = copy.deepcopy(self.load_skeleton())
        skeleton = self.auto_add_parallel_edges(skeleton)
        masteries = masteries or {}

        lines = ["flowchart TD"]

        for node in skeleton["nodes"]:
            nid = node["id"]
            name = node.get("name", nid).replace('"', "'")
            m = masteries.get(nid, 0.0)
            status = self._mastery_to_status(m)
            status_labels = {"locked": "未开始", "learning": "学习中", "mastered": "已掌握"}
            label = status_labels.get(status, status)
            pct = f"{round(m * 100)}%"
            lines.append(f'    {nid}["{name}<br/>{label} {pct}"]')

        relation_styles = {
            "depends_on": ("-->", "实线"),
            "extends": ("-.->", "虚线"),
            "parallel": ("===", "粗线"),
        }

        for edge in skeleton["edges"]:
            src = edge["source"]
            tgt = edge["target"]
            rel = edge.get("relation", "depends_on")
            arrow, _ = relation_styles.get(rel, ("-->", ""))
            rationale = edge.get("rationale", rel)
            safe_rationale = rationale.replace('"', "'")[:40]
            lines.append(f"    {src} {arrow}|\"{safe_rationale}\"| {tgt}")

        return "\n".join(lines)

    # ── LLM 补边 ──────────────────────────────────────

    async def suggest_edges(self, course_id: str | None = None) -> list[dict]:
        """LLM 自动补边：分析未连通节点对，建议遗漏的图谱关系。"""
        skeleton = self.load_skeleton()
        nodes = skeleton["nodes"]
        edges = skeleton["edges"]

        existing_pairs = {(e["source"], e["target"]) for e in edges}
        node_id_set = {n["id"] for n in nodes}

        nodes_info = [
            {"id": n["id"], "name": n.get("name", ""),
             "category": n.get("category", ""),
             "description": (n.get("description", "") or "")[:100]}
            for n in nodes
        ]
        edges_info = [
            {"source": e["source"], "target": e["target"],
             "relation": e.get("relation", ""),
             "rationale": e.get("rationale", "")}
            for e in edges
        ]

        import json as _json
        system_prompt = (
            "你是一个知识图谱专家。分析以下课程知识图谱，找出可能遗漏的学习依赖关系。\n"
            "返回一个 JSON 对象，包含 key \"suggestions\"，值为数组。每个元素含：\n"
            "  source: 源节点 id\n"
            "  target: 目标节点 id\n"
            "  relation: depends_on / extends / parallel 之一\n"
            "  rationale: 新增此边的理由（中文，20 字以内）\n"
            "  confidence: 0-1 信心分数\n"
            "不要建议已存在的边。没有建议则返回空数组。"
        )
        user_prompt = (
            f"## 节点列表\n{_json.dumps(nodes_info, ensure_ascii=False, indent=2)}\n\n"
            f"## 已有边\n{_json.dumps(edges_info, ensure_ascii=False, indent=2)}\n\n"
            f"## 已有边对 (source, target)\n{_json.dumps(sorted(existing_pairs), ensure_ascii=False)}\n\n"
            "请分析并返回建议的新边。"
        )

        try:
            from app.services.llm_service import get_llm_service
            from app.utils.json_parser import parse_llm_json
            llm = get_llm_service()
            raw = await llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )
            data = parse_llm_json(raw, fallback={}, expected_key="suggestions")
            raw_suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
        except Exception as exc:
            logger.warning("LLM edge suggestion failed: %s", exc)
            return []

        if not isinstance(raw_suggestions, list):
            return []

        suggestions = []
        name_lookup = {n["id"]: n["name"] for n in nodes_info}
        for s in raw_suggestions:
            if not isinstance(s, dict):
                continue
            src = str(s.get("source", ""))
            tgt = str(s.get("target", ""))
            if (src, tgt) in existing_pairs:
                continue
            if src not in node_id_set or tgt not in node_id_set:
                continue
            rel = s.get("relation", "extends")
            if rel not in VALID_RELATIONS:
                rel = "extends"
            try:
                confidence = float(s.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            suggestions.append({
                "source": src,
                "source_name": name_lookup.get(src, src),
                "target": tgt,
                "target_name": name_lookup.get(tgt, tgt),
                "relation": rel,
                "rationale": str(s.get("rationale", "")),
                "confidence": round(confidence, 4),
            })

        return suggestions


_graph_service: Optional[GraphService] = None
_graph_service_lock = threading.Lock()


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        with _graph_service_lock:
            if _graph_service is None:
                _graph_service = GraphService()
    return _graph_service
