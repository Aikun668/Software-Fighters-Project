"""对已保存的 content artifact 重复调用 Judge，校准稳定性。

用法:
  python scripts/calibrate_judge.py --evidence-dir temp_file/evidence --output temp_file/evidence/judge-calibration.jsonl --attempts 3
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.services.resource_quality_gate import ResourceReviewService

CONTENT_CASES = [
    ("content-transformer-basics", "面向初学者解释 Transformer 自注意力机制"),
    ("content-cnn-rnn-comparison", "对比 CNN 与 RNN 的适用场景与差异"),
    ("content-backprop-intro", "反向传播入门学习资料"),
]


def load_artifact(evidence_dir: Path, case_id: str) -> dict:
    with open(evidence_dir / f"{case_id}.artifact.json", encoding="utf-8") as f:
        return json.load(f)


async def run_all(args) -> int:
    evidence_dir = Path(args.evidence_dir)
    service = ResourceReviewService(use_mock=False)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for case_id, topic in CONTENT_CASES:
            artifact = load_artifact(evidence_dir, case_id)
            content_blocks = artifact.get("content_blocks", [])
            for attempt in range(1, args.attempts + 1):
                decision = await service.review(topic, "content", content_blocks, {})
                record = {
                    "case_id": case_id,
                    "artifact_path": str(evidence_dir / f"{case_id}.artifact.json"),
                    "attempt": attempt,
                    "status": decision.status,
                    "reason": decision.reason,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(json.dumps(record, ensure_ascii=False), flush=True)
                count += 1

    print(f"Wrote {count} calibration records to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="校准 Judge 稳定性")
    parser.add_argument("--evidence-dir", default="temp_file/evidence")
    parser.add_argument("--output", default="temp_file/evidence/judge-calibration.jsonl")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    return asyncio.run(run_all(args))


if __name__ == "__main__":
    raise SystemExit(main())
