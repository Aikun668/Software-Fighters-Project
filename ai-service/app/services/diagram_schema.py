"""交互图解 Schema v1 校验与确定性结构化 fallback。

把模型输出收敛为可验证协议：模型只输出受限的结构化图数据（schema），
服务端做确定性结构校验，客户端用受控组件渲染。不执行模型生成的 HTML/脚本。
"""

DIAGRAM_SCHEMA_VERSION = "v1"
_ALLOWED_LAYOUTS = frozenset({"layered", "flow"})
_MIN_NODES = 2
_MAX_NODES = 12
_MIN_EDGES = 1
_MAX_EDGES = 24
_MAX_LAYER = 5

# 纯文本检查：禁止 HTML 标签、URL、脚本
_FORBIDDEN_SUBSTRINGS = ("<", ">", "http://", "https://", "javascript:", "data:")


def _is_plain_text(value) -> bool:
    """纯文本：非空字符串，且不含 HTML/URL/脚本特征。"""
    if not isinstance(value, str) or not value.strip():
        return False
    low = value.lower()
    return not any(bad in low for bad in _FORBIDDEN_SUBSTRINGS)


def validate_diagram_schema(diagram) -> list[str]:
    """校验图解 Schema v1，返回问题列表（空列表 = 通过）。"""
    if not isinstance(diagram, dict):
        return ["diagram 必须是对象"]

    issues: list[str] = []

    if diagram.get("schema_version") != DIAGRAM_SCHEMA_VERSION:
        issues.append(f"schema_version 必须为 {DIAGRAM_SCHEMA_VERSION}")
    if diagram.get("layout") not in _ALLOWED_LAYOUTS:
        issues.append("layout 只能为 layered 或 flow")
    for field in ("title", "summary"):
        if not _is_plain_text(diagram.get(field)):
            issues.append(f"{field} 必须是非空纯文本")

    nodes = diagram.get("nodes")
    if not isinstance(nodes, list) or not (_MIN_NODES <= len(nodes) <= _MAX_NODES):
        issues.append(f"nodes 数量必须在 {_MIN_NODES}-{_MAX_NODES} 之间")
        nodes = []

    node_ids: list[str] = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append(f"nodes[{i}] 必须是对象")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid.strip():
            issues.append(f"nodes[{i}].id 必须非空")
        elif nid in node_ids:
            issues.append(f"nodes[{i}].id 重复：{nid}")
        else:
            node_ids.append(nid)
        if not _is_plain_text(node.get("label")):
            issues.append(f"nodes[{i}].label 必须是非空纯文本")
        if not _is_plain_text(node.get("detail")):
            issues.append(f"nodes[{i}].detail 必须是非空纯文本")
        layer = node.get("layer")
        if not isinstance(layer, int) or isinstance(layer, bool) or not (0 <= layer <= _MAX_LAYER):
            issues.append(f"nodes[{i}].layer 必须为 0-{_MAX_LAYER} 的整数")

    edges = diagram.get("edges")
    if not isinstance(edges, list) or not (_MIN_EDGES <= len(edges) <= _MAX_EDGES):
        issues.append(f"edges 数量必须在 {_MIN_EDGES}-{_MAX_EDGES} 之间")
        edges = []

    id_set = set(node_ids)
    seen_edges: set[tuple[str, str]] = set()
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            issues.append(f"edges[{i}] 必须是对象")
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not isinstance(src, str) or not isinstance(tgt, str) or src not in id_set or tgt not in id_set:
            issues.append(f"edges[{i}] 的 source/target 必须引用已存在的节点")
        elif src == tgt:
            issues.append(f"edges[{i}] 不能自环")
        else:
            key = (src, tgt)
            if key in seen_edges:
                issues.append(f"edges[{i}] 重复边：{src}->{tgt}")
            seen_edges.add(key)
        if "label" in edge and edge.get("label") not in (None, "") and not _is_plain_text(edge.get("label")):
            issues.append(f"edges[{i}].label 必须为纯文本")

    return issues


def validate_diagram_result(result) -> list[str]:
    """校验 _call_llm_json 的完整结果（顶层含 diagram 键）。"""
    if not isinstance(result, dict):
        return ["模型输出不是对象"]
    return validate_diagram_schema(result.get("diagram"))


def build_fallback_diagram(topic: str, diagram_type: str) -> dict:
    """基于主题构造最小结构化 fallback（不含 HTML/脚本）。"""
    steps = {
        "architecture": ("输入", "特征提取", "输出"),
        "training_dynamics": ("数据", "训练", "收敛"),
        "attention": ("输入", "注意力", "输出"),
        "feature_space": ("样本", "降维", "决策"),
        "algorithm": ("输入", "处理", "结果"),
    }
    l0, l1, l2 = steps.get(diagram_type, steps["architecture"])
    return {
        "schema_version": DIAGRAM_SCHEMA_VERSION,
        "title": f"{topic} 图解",
        "summary": f"{topic} 的简化流程示意。",
        "layout": "layered",
        "nodes": [
            {"id": "n0", "label": l0, "detail": f"{topic} 的起点", "layer": 0},
            {"id": "n1", "label": l1, "detail": "核心处理步骤", "layer": 1},
            {"id": "n2", "label": l2, "detail": "结果输出", "layer": 2},
        ],
        "edges": [
            {"source": "n0", "target": "n1", "label": "数据流"},
            {"source": "n1", "target": "n2", "label": "结果"},
        ],
    }
