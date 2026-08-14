"""运行记录构造测试。"""

from scripts.run_resource_workflow_cases import build_run_record


def test_record_contains_all_required_fields():
    record = build_run_record(case_id="case-1", state={"agent_name": "content"}, elapsed_ms=12)
    assert set(record) >= {
        "case_id", "run_id", "workflow_version", "route_agent", "route_strategy",
        "stage_timings", "validation_result", "review_status", "repair_attempted",
        "fallback_used", "final_status", "error_type",
    }
