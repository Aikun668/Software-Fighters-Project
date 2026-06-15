"""知识图谱服务 — 骨架加载、规则补边、掌握度注入、颜色映射、节点卡片"""

import asyncio
import copy
import json
import logging
import os
import re
import threading
from collections import deque
from typing import Any, Optional

logger = logging.getLogger(__name__)

SKELETON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "knowledge_graph_skeleton.json"
)
DYNAMIC_GRAPH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "dynamic_graphs.json"
)
VALID_RELATIONS = {"depends_on", "extends", "parallel"}

_NODE_TYPE_META: dict[str, dict[str, Any]] = {
    "concept": {
        "icon": "book",
        "theme": {"bg": "#E3F2FD", "border": "#2196F3", "text": "#0D47A1"},
        "recommended_resource_types": ["video", "article", "doc"],
    },
    "skill": {
        "icon": "tools",
        "theme": {"bg": "#E8F5E9", "border": "#4CAF50", "text": "#1B5E20"},
        "recommended_resource_types": ["exercise", "project", "video"],
    },
    "fact": {
        "icon": "check-badge",
        "theme": {"bg": "#FFF3E0", "border": "#FF9800", "text": "#E65100"},
        "recommended_resource_types": ["article", "doc", "flashcard"],
    },
}

STATUS_LOCKED = "locked"
STATUS_LEARNING = "learning"
STATUS_MASTERED = "mastered"
STATUS_FORGOTTEN = "forgotten"

_MOCK_SUB_CONCEPTS: dict[str, list[dict[str, Any]]] = {
    "ai_overview": [
        {"name": "AI 定义与图灵测试", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "AI 发展三阶段", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "ML/DL/NLP/CV 分支", "type": "concept", "mastery": 0.0, "tag": "未学"},
    ],
    "ml_basics": [
        {"name": "监督/无监督/强化学习", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "训练集/验证集/测试集", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "偏差-方差权衡", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "特征工程基础", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "dl_basics": [
        {"name": "神经元与前向传播", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "激活函数（ReLU/Sigmoid/Tanh）", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "损失函数与优化器", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "反向传播直觉理解", "type": "concept", "mastery": 0.0, "tag": "未学"},
    ],
    "transformer": [
        {"name": "Encoder-Decoder 结构", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "多头注意力机制", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "位置编码原理", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "残差连接与 LayerNorm", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "训练与推理流程", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "nlp_llm": [
        {"name": "语言模型演进史", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "预训练+微调范式", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "Prompt Engineering", "type": "skill", "mastery": 0.0, "tag": "未学"},
        {"name": "LLM 能力与局限", "type": "fact", "mastery": 0.0, "tag": "未学"},
    ],
    "backprop": [
        {"name": "链式法则矩阵形式", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "常见激活函数梯度", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "梯度消失/爆炸", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "数值稳定性技巧", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "overfitting": [
        {"name": "过拟合诊断方法", "type": "skill", "mastery": 0.0, "tag": "未学"},
        {"name": "L1/L2 正则化", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "Dropout 与 Early Stopping", "type": "skill", "mastery": 0.0, "tag": "未学"},
        {"name": "数据增强技术", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "self_attention": [
        {"name": "Q/K/V 线性变换", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "缩放点积注意力", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "多头并行机制", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "注意力权重可视化", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "gradient_variants": [
        {"name": "BGD/SGD/Mini-batch 区别", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "Momentum 加速", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "Adam 自适应学习率", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "学习率调度策略", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
    "cnn": [
        {"name": "卷积层与感受野", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "池化层与全连接层", "type": "concept", "mastery": 0.0, "tag": "未学"},
        {"name": "LeNet/AlexNet/ResNet", "type": "fact", "mastery": 0.0, "tag": "未学"},
        {"name": "CNN 训练技巧", "type": "skill", "mastery": 0.0, "tag": "未学"},
    ],
}


class GraphService:
    """知识图谱服务 — 骨架加载、规则补边、掌握度注入、颜色映射（纯算法）"""

    def __init__(self):
        self._skeleton_cache: Optional[dict[str, Any]] = None
        self._dynamic_graphs: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._dynamic_lock: threading.Lock = threading.Lock()
        self._sub_concept_cache_lock: threading.Lock = threading.Lock()
        self._load_dynamic()

    def load_skeleton(self, force_reload: bool = False) -> dict[str, Any]:
        if self._skeleton_cache is not None and not force_reload:
            return self._skeleton_cache

        with open(SKELETON_PATH, "r", encoding="utf-8") as f:
            graph = json.load(f)

        self._validate_skeleton(graph)
        self._skeleton_cache = graph
        logger.info("Skeleton %s: %d nodes, %d edges",
                    "reloaded" if force_reload else "loaded",
                    len(graph["nodes"]), len(graph["edges"]))
        return graph

    def _load_dynamic(self) -> None:
        """启动时从本地 JSON 恢复动态节点和边。"""
        if not os.path.exists(DYNAMIC_GRAPH_PATH):
            logger.info("No dynamic graph file found, starting fresh.")
            return
        try:
            with open(DYNAMIC_GRAPH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Dynamic graph file corrupted, starting fresh.")
                return
            with self._dynamic_lock:
                self._dynamic_graphs = data
            total_nodes = sum(len(v.get("nodes", [])) for v in data.values())
            total_edges = sum(len(v.get("edges", [])) for v in data.values())
            logger.info("Dynamic graphs restored: %d courses, %d nodes, %d edges",
                        len(data), total_nodes, total_edges)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load dynamic graph: %s, starting fresh.", e)

    def _save_dynamic(self) -> None:
        """add_node / add_edge / delete_node / update_node 后刷盘。

        调用方必须已持有 self._dynamic_lock，本方法不再加锁（避免死锁）。
        """
        try:
            os.makedirs(os.path.dirname(DYNAMIC_GRAPH_PATH), exist_ok=True)
            data = copy.deepcopy(self._dynamic_graphs)
            with open(DYNAMIC_GRAPH_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("Failed to save dynamic graph: %s", e)

    def _validate_skeleton(self, graph: dict[str, Any]) -> None:
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
    def _normalize_node_id(raw_id: str) -> str:
        from app.utils.graph_id import normalize_node_id
        return normalize_node_id(raw_id)

    def add_node(self, course_id: str, node: dict[str, Any]) -> dict[str, Any]:
        node_id = self._normalize_node_id(str(node.get("id", "")))
        name = node.get("name")
        if not name:
            raise ValueError("node name is required")

        skeleton_ids = {n["id"] for n in self.load_skeleton()["nodes"]}

        with self._dynamic_lock:
            dynamic = self._dynamic_graphs.setdefault(
                course_id, {"nodes": [], "edges": []}
            )
            existing_ids = skeleton_ids | {n["id"] for n in dynamic["nodes"]}
            if node_id in existing_ids:
                raise ValueError(f"node '{node_id}' already exists")

            # 语义相似度去重：新节点名称与已有节点名称余弦相似度 > 0.85 视为重复
            existing_names = [
                n["name"] for n in self.load_skeleton()["nodes"]
                if isinstance(n.get("name"), str) and n["name"]
            ] + [
                n["name"] for n in dynamic["nodes"]
                if isinstance(n.get("name"), str) and n["name"]
            ]
            try:
                from app.utils.embeddings import semantic_similarity
                for ename in existing_names:
                    if semantic_similarity(name, ename) >= 0.85:
                        raise ValueError(
                            f"节点 '{name}' 与已有节点 '{ename}' 语义重复 (相似度 >= 0.85)"
                        )
            except ImportError:
                pass  # embedding 模型未就绪时跳过去重
            except Exception as e:
                logger.warning("Semantic deduplication skipped: %s", e)

            mastery = float(node.get("mastery", 0.0))
            status = self._mastery_to_status(mastery)
            node_type = node.get("type", "concept")
            if node_type not in _NODE_TYPE_META:
                logger.warning("Unknown node type '%s', defaulting to concept", node_type)
                node_type = "concept"
            type_meta = self._get_type_meta(node_type)
            new_node: dict[str, Any] = {
                "id": node_id,
                "name": name,
                "type": node_type,
                "mastery": mastery,
                "status": status,
                "difficulty": int(node.get("difficulty", 3)),
                "color": self._mastery_to_color(mastery, status),
                "icon": type_meta["icon"],
                "theme": type_meta["theme"],
                "recommended_resource_types": type_meta["recommended_resource_types"],
            }
            dynamic["nodes"].append(new_node)
            self._save_dynamic()
            return dict(new_node)

    def add_edge(self, course_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        relation = edge.get("relation")
        if relation not in VALID_RELATIONS:
            raise ValueError(f"relation '{relation}' not in {VALID_RELATIONS}")

        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source or not target:
            raise ValueError("edge source and target are required")

        skeleton_ids = {n["id"] for n in self.load_skeleton()["nodes"]}

        with self._dynamic_lock:
            dynamic = self._dynamic_graphs.setdefault(
                course_id, {"nodes": [], "edges": []}
            )
            all_node_ids = skeleton_ids | {n["id"] for n in dynamic["nodes"]}
            if source not in all_node_ids:
                raise ValueError(f"source '{source}' does not exist")
            if target not in all_node_ids:
                raise ValueError(f"target '{target}' does not exist")

            existing_pairs = {
                (e["source"], e["target"])
                for e in self.load_skeleton()["edges"]
            } | {
                (e["source"], e["target"]) for e in dynamic["edges"]
            }
            if (source, target) in existing_pairs:
                raise ValueError(f"edge {source} -> {target} already exists")

            new_edge: dict[str, Any] = {
                "source": source,
                "target": target,
                "relation": relation,
            }
            dynamic["edges"].append(new_edge)
            self._save_dynamic()
            return dict(new_edge)

    @staticmethod
    def auto_add_parallel_edges(graph: dict[str, Any]) -> dict[str, Any]:
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

    def get_subgraph_for_topic(self, topic: str, max_nodes: int = 8) -> dict[str, Any]:
        """根据主题从骨架中裁剪相关子图。

        匹配策略：
        1. 关键词交集匹配：topic 和节点 name/description 有交集 → 种子节点
        2. BFS 1 层展开，收集种子节点 + 邻居 + 相关边
        3. 节点数超 max_nodes 时按匹配分数截断
        """
        if not topic:
            return self.load_skeleton()

        all_nodes = self._all_nodes()
        all_edges = self._all_edges()
        topic_chars = set(topic.lower())

        def _match_score(node: dict[str, Any]) -> float:
            """综合关键词 + 语义相似度打分。"""
            name = str(node.get("name", "")).lower()
            desc = str(node.get("description", "")).lower()
            keyword_hit = sum(1 for c in topic_chars if c in name or c in desc)
            score = keyword_hit / max(len(topic_chars), 1)
            if topic.lower() in name or topic.lower() in desc:
                score += 0.5
            try:
                from app.utils.embeddings import semantic_similarity
                sim = max(
                    semantic_similarity(topic, name),
                    semantic_similarity(topic, desc[:200]),
                )
                score += sim * 0.5
            except (ImportError, ValueError):
                pass
            return score

        nodes = [dict(n) for n in all_nodes]
        scored = [(n, _match_score(n)) for n in nodes]
        scored.sort(key=lambda x: -x[1])

        seed_ids = {n["id"] for n, s in scored if s > 0.1}
        if not seed_ids:
            top_n = min(3, len(scored))
            seed_ids = {scored[i][0]["id"] for i in range(top_n)}

        neighbor_ids: set[str] = set()
        for e in all_edges:
            if e["source"] in seed_ids:
                neighbor_ids.add(e["target"])
            if e["target"] in seed_ids:
                neighbor_ids.add(e["source"])

        selected_ids = seed_ids | neighbor_ids
        selected_nodes = [n for n in nodes if n["id"] in selected_ids]
        if len(selected_nodes) > max_nodes:
            selected_nodes.sort(key=lambda n: _match_score(n), reverse=True)
            selected_nodes = selected_nodes[:max_nodes]
            selected_ids = {n["id"] for n in selected_nodes}

        selected_edges = [
            dict(e) for e in all_edges
            if e["source"] in selected_ids and e["target"] in selected_ids
        ]

        logger.info("Subgraph for topic '%s': %d nodes, %d edges",
                    topic, len(selected_nodes), len(selected_edges))
        return {"nodes": selected_nodes, "edges": selected_edges}

    async def get_graph(self, course_id: str, masteries: dict[str, float] | None = None) -> dict[str, Any]:
        graph = copy.deepcopy(self.load_skeleton())

        with self._dynamic_lock:
            dynamic = copy.deepcopy(
                self._dynamic_graphs.get(course_id, {"nodes": [], "edges": []})
            )

        existing_node_ids = {n["id"] for n in graph["nodes"]}
        for node in dynamic["nodes"]:
            if node["id"] not in existing_node_ids:
                graph["nodes"].append(node)
                existing_node_ids.add(node["id"])

        seen_edges = {(e["source"], e["target"]) for e in graph["edges"]}
        for edge in dynamic["edges"]:
            key = (edge["source"], edge["target"])
            if key not in seen_edges:
                graph["edges"].append(edge)
                seen_edges.add(key)

        graph = self.auto_add_parallel_edges(graph)

        masteries = masteries or {}
        for node in graph["nodes"]:
            m = masteries.get(node["id"], 0.0)
            status = self._mastery_to_status(m)
            node["mastery"] = m
            node["status"] = status
            node["color"] = self._mastery_to_color(m, status)
            type_meta = self._get_type_meta(node.get("type", "concept"))
            node["icon"] = type_meta["icon"]
            node["theme"] = type_meta["theme"]
            node["recommended_resource_types"] = type_meta["recommended_resource_types"]

        return graph

    async def get_node_card(self, node_id: str,
                            course_id: str = "ai_intro",
                            masteries: dict[str, float] | None = None,
                            total_exercises: int = 0,
                            last_practiced: str | None = None) -> dict[str, Any]:
        """获取节点卡片详情。同时搜索骨架和动态节点。所有数据由 Java 传入。"""
        skeleton = self.load_skeleton()
        with self._dynamic_lock:
            dynamic = self._dynamic_graphs.get(course_id, {"nodes": [], "edges": []})

        node = None
        for n in skeleton["nodes"]:
            if n["id"] == node_id:
                node = dict(n)
                break
        if node is None:
            for n in dynamic["nodes"]:
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
        type_meta = self._get_type_meta(node.get("type", "concept"))
        node["icon"] = type_meta["icon"]
        node["theme"] = type_meta["theme"]
        node["recommended_resource_types"] = type_meta["recommended_resource_types"]

        node_map = {n["id"]: n for n in skeleton["nodes"]}
        for n in dynamic["nodes"]:
            node_map[n["id"]] = n
        all_edges = skeleton["edges"] + dynamic["edges"]
        predecessors = [e["source"] for e in all_edges if e["target"] == node_id]
        successors = [e["target"] for e in all_edges if e["source"] == node_id]
        related = [
            e["source"] if e["target"] == node_id else e["target"]
            for e in all_edges
            if (e["source"] == node_id or e["target"] == node_id)
            and e["relation"] in ("parallel", "extends")
        ]

        def _context_detail(nid: str) -> dict[str, Any]:
            m = masteries.get(nid, 0.0)
            s = GraphService._mastery_to_status(m)
            return {
                "id": nid,
                "name": node_map.get(nid, {}).get("name", nid),
                "status": s, "mastery": m,
                "color": GraphService._mastery_to_color(m, s),
            }

        sub_concepts = _MOCK_SUB_CONCEPTS.get(node_id, [])
        if not sub_concepts and node_id not in _MOCK_SUB_CONCEPTS:
            sub_concepts = await self._generate_sub_concepts(node_id, node)

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
    def _get_type_meta(node_type: str) -> dict[str, Any]:
        return _NODE_TYPE_META.get(node_type, _NODE_TYPE_META["concept"])

    async def _generate_sub_concepts(self, node_id: str,
                                     node: dict[str, Any]) -> list[dict[str, Any]]:
        """为动态节点或未预设子概念的骨架节点，用 LLM 生成子概念列表（带缓存 + inflight 合并）。"""
        if not hasattr(self, "_sub_concept_cache"):
            self._sub_concept_cache: dict[str, list[dict[str, Any]]] = {}
        if not hasattr(self, "_sub_concept_inflight"):
            self._sub_concept_inflight: dict[str, asyncio.Event] = {}

        with self._sub_concept_cache_lock:
            if node_id in self._sub_concept_cache:
                return self._sub_concept_cache[node_id]
            if node_id in self._sub_concept_inflight:
                event = self._sub_concept_inflight[node_id]
                is_owner = False
            else:
                event = asyncio.Event()
                self._sub_concept_inflight[node_id] = event
                is_owner = True

        if not is_owner:
            await event.wait()
            with self._sub_concept_cache_lock:
                return self._sub_concept_cache.get(
                    node_id,
                    [{"name": f"{node.get('name', node_id)}基础", "type": "concept",
                      "mastery": 0.0, "tag": "未学"}],
                )

        name = str(node.get("name", node_id))
        node_type = str(node.get("type", "concept"))
        description = str(node.get("description", name))
        result: list[dict[str, Any]] = []

        try:
            from app.services.llm_service import get_llm_service

            system_prompt = (
                "你是课程知识点专家。针对给定的知识点节点，请分解出 3-4 个子概念。"
                "每个子概念输出 JSON: {\"name\": \"...\", \"type\": \"concept|skill|fact\"}"
                "输出格式: {\"sub_concepts\": [...]}"
            )
            user_prompt = (
                f"知识点: {name}\n类型: {node_type}\n描述: {description[:300]}\n\n"
                "请分解此知识点的 3-4 个子概念。"
            )
            llm = get_llm_service()
            response = await llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )
            from app.utils.json_parser import parse_llm_json
            data = parse_llm_json(response, fallback={}, expected_key="sub_concepts")
            sub = data.get("sub_concepts", []) if isinstance(data, dict) else []
            if isinstance(sub, list) and sub:
                result = [
                    {"name": str(sc.get("name", "")),
                     "type": str(sc.get("type", "concept")),
                     "mastery": 0.0, "tag": "未学"}
                    for sc in sub if isinstance(sc, dict) and sc.get("name")
                ]
        except Exception as e:
            logger.warning("Failed to generate sub_concepts for '%s': %s", node_id, e)

        if not result:
            result = [{"name": f"{name}基础", "type": "concept", "mastery": 0.0, "tag": "未学"}]

        with self._sub_concept_cache_lock:
            self._sub_concept_cache[node_id] = result
            event.set()
            self._sub_concept_inflight.pop(node_id, None)
        return result

    @staticmethod
    def _mastery_to_status(mastery: float) -> str:
        if mastery <= 0.0:
            return STATUS_LOCKED
        elif mastery < 0.85:
            return STATUS_LEARNING
        else:
            return STATUS_MASTERED

    @staticmethod
    def _mastery_to_color(mastery: float, status: str) -> dict[str, str]:
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
    def _build_actions(mastery: float, status: str) -> list[dict[str, Any]]:
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

    def _all_nodes(self, course_id: str = "ai_intro") -> list[dict[str, Any]]:
        """合并骨架 + 动态节点（线程安全读）。"""
        skeleton = self.load_skeleton()
        with self._dynamic_lock:
            dynamic = copy.deepcopy(
                self._dynamic_graphs.get(course_id, {"nodes": [], "edges": []})
            )
        return list(skeleton["nodes"]) + list(dynamic["nodes"])

    def _all_edges(self, course_id: str = "ai_intro") -> list[dict[str, Any]]:
        """合并骨架 + 动态边（线程安全读）。"""
        skeleton = self.load_skeleton()
        with self._dynamic_lock:
            dynamic = copy.deepcopy(
                self._dynamic_graphs.get(course_id, {"nodes": [], "edges": []})
            )
        return list(skeleton["edges"]) + list(dynamic["edges"])

    def get_successors(self, node_id: str, course_id: str = "ai_intro") -> list[str]:
        edges = self._all_edges(course_id)
        return [e["target"] for e in edges if e["source"] == node_id]

    def get_predecessors(self, node_id: str, course_id: str = "ai_intro") -> list[str]:
        edges = self._all_edges(course_id)
        return [e["source"] for e in edges if e["target"] == node_id]

    def topological_sort(self, course_id: str = "ai_intro") -> list[str]:
        nodes = {n["id"] for n in self._all_nodes(course_id)}
        edges = self._all_edges(course_id)

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
            return [n["id"] for n in self._all_nodes(course_id)]

        return result

    def get_critical_path(self, start_node: str, end_node: str,
                          course_id: str = "ai_intro") -> list[str]:
        nodes = {n["id"] for n in self._all_nodes(course_id)}
        if start_node not in nodes or end_node not in nodes:
            return []

        edges = self._all_edges(course_id)
        adj = {nid: [] for nid in nodes}
        for e in edges:
            src, tgt = e["source"], e["target"]
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)

        topo = self.topological_sort(course_id)
        dist: dict[str, float] = {nid: float("-inf") for nid in nodes}
        parent: dict[str, str | None] = {nid: None for nid in nodes}
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

    # ── Phase A: 图谱分析 ────────────────────────────────────

    def recommend_next_node(self, masteries: dict[str, float],
                            course_id: str = "ai_intro") -> list[dict[str, Any]]:
        """知识缺口分析：推荐下一个该学的节点。

        规则：所有前置节点 mastery >= 0.6 且自身 mastery < 0.85 的节点，
        按优先级排序（依赖链短的优先、自身 mastery 低的优先）。
        """
        nodes = {n["id"]: n for n in self._all_nodes(course_id)}
        masteries = masteries or {}
        PREREQ_THRESHOLD = 0.6

        candidates: list[dict[str, Any]] = []
        for node_id, node in nodes.items():
            current = masteries.get(node_id, 0.0)
            if current >= 0.85:
                continue

            predecessors = self.get_predecessors(node_id)
            all_prereqs_met = all(
                masteries.get(pid, 0.0) >= PREREQ_THRESHOLD
                for pid in predecessors
            )
            if not all_prereqs_met:
                continue

            prereq_count = len(predecessors)
            priority = (1.0 - current) * 0.7 + min(prereq_count / 10.0, 1.0) * 0.3
            candidates.append({
                "node_id": node_id,
                "name": node.get("name", node_id),
                "current_mastery": current,
                "priority": round(priority, 3),
                "reason": "已解锁，掌握度较低" if current < 0.3 else "已解锁，继续巩固",
            })

        candidates.sort(key=lambda c: -c["priority"])
        return candidates[:3]

    def get_progress_summary(self, masteries: dict[str, float],
                             course_id: str = "ai_intro") -> dict[str, Any]:
        """学习进度概要：全局掌握率 + 各分类统计。"""
        nodes = [dict(n) for n in self._all_nodes(course_id)]
        masteries = masteries or {}

        total = len(nodes)
        if total == 0:
            return {"total": 0, "mastered": 0, "learning": 0, "locked": 0,
                    "overall_mastery": 0.0, "by_category": {}}

        by_category: dict[str, dict[str, Any]] = {}
        for node in nodes:
            nid = node["id"]
            m = masteries.get(nid, 0.0)
            status = self._mastery_to_status(m)
            category = str(node.get("category", "未分类"))

            if category not in by_category:
                by_category[category] = {"total": 0, "mastered": 0, "learning": 0, "locked": 0, "avg_mastery": 0.0}
            cat = by_category[category]
            cat["total"] += 1
            if status == STATUS_MASTERED:
                cat["mastered"] += 1
            elif status == STATUS_LOCKED:
                cat["locked"] += 1
            else:
                cat["learning"] += 1
            cat["avg_mastery"] += m

        for cat in by_category.values():
            if cat["total"] > 0:
                cat["avg_mastery"] = round(cat["avg_mastery"] / cat["total"], 2)

        status_counts = {"mastered": 0, "learning": 0, "locked": 0}
        for node in nodes:
            status = self._mastery_to_status(masteries.get(node["id"], 0.0))
            status_counts[status] += 1

        overall = round(sum(masteries.get(n["id"], 0.0) for n in nodes) / total, 2)

        return {
            "total": total,
            **status_counts,
            "overall_mastery": overall,
            "by_category": by_category,
        }

    def check_prerequisites(self, node_id: str, masteries: dict[str, float],
                            threshold: float = 0.6,
                            course_id: str = "ai_intro") -> dict[str, Any]:
        """前置条件检查：用户是否满足学习某节点的前置条件。"""
        node_map = {n["id"]: n for n in self._all_nodes(course_id)}
        if node_id not in node_map:
            return {"can_study": False, "error": f"节点 '{node_id}' 不存在", "missing": []}

        masteries = masteries or {}
        predecessors = self.get_predecessors(node_id)
        if not predecessors:
            return {"can_study": True, "missing": [], "node": {
                "id": node_id, "name": node_map[node_id].get("name", node_id),
            }}

        missing: list[dict[str, Any]] = []
        for pid in predecessors:
            current = masteries.get(pid, 0.0)
            if current < threshold:
                missing.append({
                    "node_id": pid,
                    "name": node_map.get(pid, {}).get("name", pid),
                    "current_mastery": current,
                    "required_mastery": threshold,
                })

        return {
            "can_study": len(missing) == 0,
            "node": {"id": node_id, "name": node_map[node_id].get("name", node_id)},
            "missing": missing,
        }

    # ── Phase B: 图谱维护 ────────────────────────────────────

    def delete_node(self, course_id: str, node_id: str) -> bool:
        """从动态图中删除节点（骨架节点不可删）。"""
        skeleton_ids = {n["id"] for n in self.load_skeleton()["nodes"]}
        if node_id in skeleton_ids:
            raise ValueError(f"骨架节点 '{node_id}' 不可删除，只能删除动态添加的节点")

        with self._dynamic_lock:
            dynamic = self._dynamic_graphs.get(course_id)
            if not dynamic:
                return False
            before = len(dynamic["nodes"])
            dynamic["nodes"] = [n for n in dynamic["nodes"] if n["id"] != node_id]
            dynamic["edges"] = [
                e for e in dynamic["edges"]
                if e["source"] != node_id and e["target"] != node_id
            ]
            if len(dynamic["nodes"]) < before:
                self._save_dynamic()
                return True
        return False

    def update_node(self, course_id: str, node_id: str,
                    updates: dict[str, Any]) -> dict[str, Any]:
        """更新节点元数据（动态节点全字段可改，骨架节点仅限 difficulty/category）。"""
        skeleton_ids = {n["id"] for n in self.load_skeleton()["nodes"]}
        is_skeleton = node_id in skeleton_ids

        if is_skeleton:
            skeleton = copy.deepcopy(self.load_skeleton())
            for n in skeleton["nodes"]:
                if n["id"] == node_id:
                    if "difficulty" in updates:
                        n["difficulty"] = max(1, min(5, int(updates["difficulty"])))
                    if "category" in updates:
                        n["category"] = str(updates["category"])
                    return dict(n)
            raise ValueError(f"骨架节点 '{node_id}' 未找到")

        with self._dynamic_lock:
            dynamic = self._dynamic_graphs.setdefault(
                course_id, {"nodes": [], "edges": []}
            )
            for n in dynamic["nodes"]:
                if n["id"] == node_id:
                    for key in ("name", "description", "difficulty", "category", "type"):
                        if key in updates:
                            n[key] = updates[key]
                    if "difficulty" in updates:
                        n["difficulty"] = max(1, min(5, int(updates["difficulty"])))
                    self._save_dynamic()
                    return dict(n)
        raise ValueError(f"动态节点 '{node_id}' 未找到")

    async def suggest_edges(self, course_id: str) -> list[dict[str, Any]]:
        """LLM 自动补边：检查未连接节点对，建议遗漏的图谱关系。"""
        all_nodes = self._all_nodes(course_id)
        all_edges = self._all_edges(course_id)
        nodes = {n["id"]: n for n in all_nodes}
        node_ids = list(nodes.keys())
        existing_pairs = {
            (e["source"], e["target"]) for e in all_edges
        } | {(e["target"], e["source"]) for e in all_edges}

        # 收集候选节点对（difference 不超过 2 级）
        import math
        pairs: list[tuple[str, str]] = []
        for i, a in enumerate(node_ids):
            for b in node_ids[i + 1:]:
                if (a, b) not in existing_pairs:
                    diff = abs(
                        nodes[a].get("difficulty", 3) - nodes[b].get("difficulty", 3)
                    )
                    if diff <= 2:
                        pairs.append((a, b))
        if not pairs:
            return []

        # 取前 8 对用 LLM 分析
        import asyncio
        sample = pairs[:8]

        async def _analyze_one(a: str, b: str) -> dict[str, Any] | None:
            try:
                from app.services.llm_service import get_llm_service
                from app.utils.json_parser import parse_llm_json

                na, nb = nodes[a].get("name", a), nodes[b].get("name", b)
                da, db = nodes[a].get("description", "")[:150], nodes[b].get("description", "")[:150]

                llm = get_llm_service()
                response = await llm.chat(
                    [{"role": "user", "content": (
                        f"节点A: {na}\n描述: {da}\n"
                        f"节点B: {nb}\n描述: {db}\n\n"
                        "判断这两个知识点之间是否存在关系。可选关系类型："
                        "depends_on（A是B的前置）、extends（A延伸出B）、"
                        "parallel（同级概念）、none（无关系）。"
                        "输出 JSON: {\"relation\": \"depends_on\", \"rationale\": \"理由\", \"confidence\": 0.9}"
                    )}],
                    system_prompt="你是课程知识图谱专家，判断知识点之间的关系。",
                )
                data = parse_llm_json(response, fallback={}, expected_key="relation")
                if data and isinstance(data, dict) and data.get("relation") != "none":
                    rel = str(data.get("relation", ""))
                    if rel in ("depends_on", "extends", "parallel"):
                        return {
                            "source": a, "target": b,
                            "relation": rel,
                            "rationale": str(data.get("rationale", "")),
                            "confidence": float(data.get("confidence", 0.5)),
                        }
            except Exception as e:
                logger.warning("Edge suggestion failed for %s-%s: %s", a, b, e)
            return None

        tasks = [_analyze_one(a, b) for a, b in sample]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    # ── Phase C: 可视化 ──────────────────────────────────────

    def export_mermaid(self, course_id: str = "ai_intro",
                       masteries: dict[str, float] | None = None) -> str:
        """导出知识图谱为 Mermaid flowchart 语法（合并骨架 + 动态节点/边）。"""
        nodes = self._all_nodes(course_id)
        edges = self._all_edges(course_id)
        masteries = masteries or {}
        node_map = {n["id"]: n for n in nodes}

        lines = ["graph TD"]
        for nid, node in node_map.items():
            m = masteries.get(nid, 0.0)
            name = node.get("name", nid).replace('"', "'")
            lines.append(
                f'    {nid}["{name}<br/>掌握度: {m:.0%}"]:::status_{self._mastery_to_status(m)}'
            )

        for e in edges:
            src, tgt, rel = e["source"], e["target"], e.get("relation", "")
            label = {"depends_on": "→", "extends": "⇒", "parallel": "⇔"}.get(rel, "→")
            lines.append(f"    {src} -->|{label}| {tgt}")

        lines.extend([
            "    classDef status_mastered fill:#C8DFF5,stroke:#4A8EC4",
            "    classDef status_learning fill:#D6E8F0,stroke:#6AA3C4",
            "    classDef status_locked fill:#E8E8ED,stroke:#C4C4CC",
            "    classDef status_forgotten fill:#F5E6D6,stroke:#E07A3A",
        ])
        return "\n".join(lines)

    def get_layered_graph(self, masteries: dict[str, float] | None = None,
                          course_id: str = "ai_intro") -> dict[str, Any]:
        """返回带层级信息的图谱（用于前端分层布局，含动态节点）。"""
        all_nodes = self._all_nodes(course_id)
        all_edges = self._all_edges(course_id)
        graph = {"nodes": copy.deepcopy(all_nodes), "edges": copy.deepcopy(all_edges)}
        masteries = masteries or {}

        predecessors = {n["id"]: self.get_predecessors(n["id"], course_id)
                        for n in graph["nodes"]}
        layers: dict[str, int] = {}
        for nid in self.topological_sort(course_id):
            prereqs = predecessors.get(nid, [])
            if not prereqs:
                layers[nid] = 0
            else:
                layers[nid] = max(layers.get(pid, 0) for pid in prereqs) + 1

        for node in graph["nodes"]:
            nid = node["id"]
            m = masteries.get(nid, 0.0)
            status = self._mastery_to_status(m)
            node["mastery"] = m
            node["status"] = status
            node["color"] = self._mastery_to_color(m, status)
            node["layer"] = layers.get(nid, 0)

        return graph


_graph_service: Optional[GraphService] = None
_graph_service_lock = threading.Lock()


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        with _graph_service_lock:
            if _graph_service is None:
                _graph_service = GraphService()
    return _graph_service
