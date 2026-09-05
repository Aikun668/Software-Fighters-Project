"""评测运行器与回归门禁测试（对话底座救援 · Task 10）。

运行器绕开页面，直接调用同一个聊天入口（ChatCenter）；用假客户端离线跑
60 条评测，产出带 UTC 时间戳的报告；路由/SSE 退化必须非零退出。
"""
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from evals.run_chat_eval import (  # noqa: E402
    FakeEvalClient,
    check_gates,
    evaluate_dataset,
    load_samples,
    main,
    write_report,
)

DATASET = PROJECT_ROOT / "evals" / "chat_foundation_v1.jsonl"


# ═══════════════════════════════════════════════════════════════
# 计划要求的失败测试：假客户端跑 60 条 + 报告字段齐全
# ═══════════════════════════════════════════════════════════════

class TestRunnerContract:
    @pytest.mark.asyncio
    async def test_fake_client_runs_all_60_samples(self):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        assert report["total"] == 60
        assert len(report["records"]) == 60
        # 计划要求的报告字段
        assert "capability_false_trigger_rate" in report
        assert "capability_recognition_rate" in report
        assert "sse_done_rate" in report
        assert isinstance(report["needs_review"], list)

    @pytest.mark.asyncio
    async def test_offline_routing_metrics_hit_gates(self):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        # Task 9 已验证数据集与 CapabilityGate 零分歧，离线指标应为满分
        assert report["capability_false_trigger_rate"] == 0.0
        assert report["capability_recognition_rate"] == 1.0
        assert report["sse_done_rate"] == 1.0
        gates = check_gates(report)
        assert all(gates.values()), gates

    @pytest.mark.asyncio
    async def test_every_record_has_machine_checks_and_sanity(self):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        for rec in report["records"]:
            assert set(rec["machine_checks"]) >= {"route", "sse_done", "orchestration_entered", "must_include", "must_not_include"}
            assert "sanity_verdict" in rec and rec["sanity_verdict"] in ("ACCEPT", "RETRY_ONCE", "USER_SAFE_ERROR")
            assert rec["terminal_event"] in ("done", "error", "inquiry", "timeout", None)

    @pytest.mark.asyncio
    async def test_normal_scoped_done_rate_present(self):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        # rubric 口径：done 率按普通问答（52 条）计
        assert report["normal_sse_done_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_needs_review_entries_have_reasons(self):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        for item in report["needs_review"]:
            assert item["id"]
            assert item["reason"]


# ═══════════════════════════════════════════════════════════════
# 报告落盘：UTC ISO-8601 时间戳命名；不写私密历史
# ═══════════════════════════════════════════════════════════════

class TestReportPersistence:
    @pytest.mark.asyncio
    async def test_report_file_named_with_utc_timestamp(self, tmp_path):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        out = write_report(report, tmp_path)
        assert re.fullmatch(
            r"chat_foundation_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.json", out.name
        ), out.name
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["total"] == 60

    @pytest.mark.asyncio
    async def test_report_does_not_leak_private_history(self, tmp_path):
        report = await evaluate_dataset(DATASET, client=FakeEvalClient())
        raw = json.dumps(report, ensure_ascii=False)
        for sample in load_samples(DATASET):
            # 不写完整私密历史：current_message 与 turns 正文一律不落报告
            assert sample["current_message"] not in raw, sample["id"]
            for turn in sample.get("turns", []):
                content = turn.get("content", "")
                if len(content) >= 8:
                    assert content not in raw, sample["id"]


# ═══════════════════════════════════════════════════════════════
# 回归门禁：路由/SSE 退化必须非零退出
# ═══════════════════════════════════════════════════════════════

class TestGateExits:
    @pytest.mark.asyncio
    async def test_healthy_dataset_exits_zero(self, tmp_path, capsys):
        code = await main(["--dataset", str(DATASET), "--out-dir", str(tmp_path)])
        assert code == 0

    @pytest.mark.asyncio
    async def test_routing_regression_exits_nonzero(self, tmp_path, capsys):
        # 构造一条"期望 NORMAL_CHAT 但实际会进 EXERCISE"的退化样例
        bad = {
            "id": "bad-01", "category": "normal_qa", "turns": [],
            "current_message": "帮我出 5 道进程调度选择题",
            "expected_route": "NORMAL_CHAT", "must_include": ["题"],
            "must_not_include": [], "evaluator_notes": "门禁回归用例",
        }
        ds = tmp_path / "bad_dataset.jsonl"
        ds.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        code = await main(["--dataset", str(ds), "--out-dir", str(tmp_path)])
        assert code == 1
        report = json.loads((tmp_path / sorted(p.name for p in tmp_path.glob("chat_foundation_*.json"))[-1]).read_text(encoding="utf-8"))
        assert report["capability_false_trigger_rate"] > 0.05

    @pytest.mark.asyncio
    async def test_sse_regression_exits_nonzero(self, tmp_path):
        # 终止事件不是 done 的比例超门槛 → 非零退出
        class BrokenClient:
            async def run(self, sample):
                return "这是一个用于门禁测试的正常回答内容。", "error"

        code = await main(["--dataset", str(DATASET), "--out-dir", str(tmp_path), "--client", "broken"])
        assert code == 1
