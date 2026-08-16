"""图解 Schema v1 校验器与确定性 fallback 测试。"""

from app.services.diagram_schema import (
    DIAGRAM_SCHEMA_VERSION,
    validate_diagram_schema,
    build_fallback_diagram,
)


def _valid_diagram() -> dict:
    return {
        "schema_version": "v1",
        "title": "CNN 数据流",
        "summary": "输入图像依次通过卷积、池化和分类层。",
        "layout": "layered",
        "nodes": [
            {"id": "input", "label": "输入图像", "detail": "原始像素张量", "layer": 0},
            {"id": "conv", "label": "卷积层", "detail": "提取局部特征", "layer": 1},
            {"id": "out", "label": "输出", "detail": "分类结果", "layer": 2},
        ],
        "edges": [
            {"source": "input", "target": "conv", "label": "特征图"},
            {"source": "conv", "target": "out", "label": "分类"},
        ],
    }


def test_valid_diagram_passes():
    assert validate_diagram_schema(_valid_diagram()) == []


def test_duplicate_node_id_rejected():
    d = _valid_diagram()
    d["nodes"][1]["id"] = "input"
    issues = validate_diagram_schema(d)
    assert any("重复" in i for i in issues)


def test_dangling_edge_rejected():
    d = _valid_diagram()
    d["edges"].append({"source": "input", "target": "missing", "label": "x"})
    issues = validate_diagram_schema(d)
    assert any("引用" in i for i in issues)


def test_out_of_range_layer_rejected():
    d = _valid_diagram()
    d["nodes"][0]["layer"] = 6
    issues = validate_diagram_schema(d)
    assert any("layer" in i for i in issues)


def test_wrong_schema_version_rejected():
    d = _valid_diagram()
    d["schema_version"] = "v2"
    issues = validate_diagram_schema(d)
    assert any("schema_version" in i for i in issues)


def test_html_in_label_rejected():
    d = _valid_diagram()
    d["nodes"][0]["label"] = "<b>输入</b>"
    issues = validate_diagram_schema(d)
    assert any("label" in i for i in issues)


def test_fallback_diagram_is_valid():
    fb = build_fallback_diagram("CNN", "architecture")
    assert validate_diagram_schema(fb) == []
    assert fb["schema_version"] == DIAGRAM_SCHEMA_VERSION
    assert len(fb["nodes"]) >= 2
    assert len(fb["edges"]) >= 1
