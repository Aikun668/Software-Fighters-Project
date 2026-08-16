"""运行固定资源案例，产出 JSONL 运行记录（用于质量门控前后对比证据）。

用法:
  python scripts/run_resource_workflow_cases.py --mode mock --quality-mode off --output temp_file/evidence/baseline-mock.jsonl
  python scripts/run_resource_workflow_cases.py --mode mock --quality-mode shadow --output temp_file/evidence/shadow-mock.jsonl
  python scripts/run_resource_workflow_cases.py --mode real --quality-mode active --output temp_file/evidence/active-real.jsonl
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 必须先加载 .env，再导入 app（llm_service 在 import 时读取环境变量）
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.workflows.resource_gen import ResourceGenWorkflow

WORKFLOW_VERSION = "resource-quality-gate-v1"


def build_run_record(case_id: str, state: dict, elapsed_ms: int) -> dict:
    """从一次运行的 state 构造最小运行记录字段。"""
    return {
        "case_id": case_id,
        "run_id": state.get("run_id", ""),
        "workflow_version": WORKFLOW_VERSION,
        "route_agent": state.get("agent_name", ""),
        "route_strategy": state.get("route_strategy", ""),
        "stage_timings": state.get("stage_timings", {}),
        "validation_result": state.get("validation_result", {}),
        "review_status": state.get("review_status", "not_applicable"),
        "repair_attempted": state.get("repair_attempted", False),
        "fallback_used": state.get("fallback_used", False),
        "final_status": state.get("final_status", ""),
        "error_type": state.get("error_type", ""),
        "diagram_source": state.get("diagram_source", ""),
        "diagram_schema_version": state.get("diagram_schema_version", ""),
        "elapsed_ms": elapsed_ms,
    }


def load_cases(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_one(workflow: ResourceGenWorkflow, case: dict) -> dict:
    started = time.perf_counter()
    try:
        state = await workflow.run({
            "topic": case["topic"],
            "resource_type": case.get("resource_type", ""),
            "student_profile": case.get("student_profile", {}),
            "user_id": 1,
        })
    except Exception as e:
        state = {"final_status": "error", "error_type": type(e).__name__}
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return build_run_record(case["case_id"], state, elapsed_ms)


async def run_all(args) -> int:
    cases = load_cases(args.cases)
    use_mock = args.mode == "mock"
    workflow = ResourceGenWorkflow(use_mock=use_mock, quality_mode=args.quality_mode)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for case in cases:
            record = await run_one(workflow, case)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(json.dumps(record, ensure_ascii=False))
            count += 1

    print(f"Wrote {count} records to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="运行资源生成案例并产出 JSONL 证据")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--quality-mode", choices=["off", "shadow", "active"], default="shadow")
    parser.add_argument("--output", required=True, help="JSONL 输出路径")
    parser.add_argument("--cases", default="tests/fixtures/resource_workflow_cases.json")
    args = parser.parse_args()
    return asyncio.run(run_all(args))


if __name__ == "__main__":
    raise SystemExit(main())
