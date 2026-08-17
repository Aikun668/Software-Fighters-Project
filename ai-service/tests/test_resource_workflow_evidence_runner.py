"""运行记录构造测试。"""

from scripts.run_resource_workflow_cases import build_run_record, _extract_diagram


def test_record_contains_all_required_fields():
    record = build_run_record(case_id="case-1", state={"agent_name": "content"}, elapsed_ms=12)
    assert set(record) >= {
        "case_id", "run_id", "workflow_version", "route_agent", "route_strategy",
        "stage_timings", "validation_result", "review_status", "review_reason",
        "repair_attempted", "fallback_used", "final_status", "error_type",
        "diagram_source", "diagram_schema_version", "diagram_artifact_path",
        "artifact_path",
    }


def test_extract_diagram_returns_diagram_for_interactive_block():
    state = {"content_blocks": [{
        "type": "interactive_diagram",
        "heading": "CNN",
        "content": "摘要",
        "diagram": {"schema_version": "v1", "title": "CNN"},
    }]}
    assert _extract_diagram(state) == {"schema_version": "v1", "title": "CNN"}


def test_extract_diagram_returns_none_for_content():
    state = {"content_blocks": [{"type": "section", "heading": "概述", "content": "文本"}]}
    assert _extract_diagram(state) is None
