"""普通聊天稳定性回归测试（chat_stability_v1 · 全离线）。

对应运行器：evals/run_stability_regress.py；数据集：evals/chat_stability_v1.jsonl（19 条）。
覆盖五类稳定性风险：普通提问误触发能力、二轮追问丢上下文、空回答/泄露降级、
错误终态可观测性、无关画像干扰。全部断言离线可判定（真实 CapabilityGate /
ContextBuilder / ResponseSanity 合同 + mock Tutor，不调真实 LLM）。

实战记录（2026-09-06）：本套件首个版本的 E2E 用例抓到工作区未提交改动在
`_run_tutor`（auto_center.py:84）引用未定义 `context` 的 NameError——该缺陷会让
所有普通聊天返回"答疑失败"。该行随后被修正为
`(task.context or {}).get("conversation_id")`，本测试当前转绿并长期守护该接线。
"""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from evals.run_stability_regress import (  # noqa: E402
    DATASET,
    check_gates,
    evaluate_dataset,
    load_samples,
    main,
)

from app.agents.tutor_agent import TutorAgent  # noqa: E402
from app.centers.auto_center import AutoCenter  # noqa: E402
from app.centers import result_agent as result_agent_module  # noqa: E402
from app.centers.chat_center import ChatCenter  # noqa: E402
from app.centers.result_agent import ResultAgent  # noqa: E402
from app.events.types import StreamEventType  # noqa: E402
from app.services.capability_gate import CapabilityGate  # noqa: E402
from app.services.context_builder import ContextBuilder  # noqa: E402

SAMPLES = load_samples(DATASET)
SAMPLES_BY_ID = {s["id"]: s for s in SAMPLES}

REQUIRED_FIELDS = {
    "id", "category", "turns", "current_message", "expected_route",
    "expected_task_mode", "expected_terminal", "expect_content",
}
EXPECTED_CATEGORIES = {
    "concept_qa", "compare_qa", "study_advice", "followup_2turn",
    "capability_request", "noise_robustness", "fault_injection",
}
LEAK_MARKERS = ("system_prompt", "student_profile", "built_context", "messages_history")


# ═══════════════════════ 数据集完整性 ═══════════════════════

class TestDatasetIntegrity:
    def test_case_count_within_budget(self):
        assert 12 <= len(SAMPLES) <= 20, f"回归集应保持小而稳（12~20 条），当前 {len(SAMPLES)}"

    def test_unique_ids_and_required_fields(self):
        ids = [s["id"] for s in SAMPLES]
        assert len(ids) == len(set(ids))
        for s in SAMPLES:
            assert REQUIRED_FIELDS <= set(s), (s["id"], REQUIRED_FIELDS - set(s))
            assert s["expected_route"] in {"NORMAL_CHAT", "PLAN", "RESOURCE", "EXERCISE", "VISUALIZATION"}
            assert s["expected_terminal"] in {"done", "error"}

    def test_categories_cover_stability_groups(self):
        assert {s["category"] for s in SAMPLES} == EXPECTED_CATEGORIES

    def test_route_calibration_zero_divergence(self):
        """expected_route 必须与真实 CapabilityGate 零分歧（防标定漂移）。"""
        gate = CapabilityGate()
        divergences = []
        for s in SAMPLES:
            if not s["current_message"].strip():
                continue  # 空输入不走能力判定（inquiry 路径）
            actual = gate.decide(s["current_message"], mode="auto").kind.value
            if actual != s["expected_route"]:
                divergences.append((s["id"], s["expected_route"], actual))
        assert not divergences, divergences


# ═══════════════════════ 离线运行器与门禁 ═══════════════════════

class TestOfflineRunnerGates:
    @pytest.mark.asyncio
    async def test_full_run_passes_all_gates(self):
        report = await evaluate_dataset(DATASET)
        assert report["total"] == len(SAMPLES)
        assert not report["failed_cases"], report["failed_cases"]
        assert not report["route_calibration_divergences"]
        assert all(check_gates(report).values()), check_gates(report)

    @pytest.mark.asyncio
    async def test_main_exits_zero_and_writes_utc_report(self, tmp_path):
        code = await main(["--dataset", str(DATASET), "--out-dir", str(tmp_path)])
        assert code == 0
        reports = list(tmp_path.glob("chat_stability_*.json"))
        assert len(reports) == 1
        assert re.fullmatch(r"chat_stability_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.json",
                            reports[0].name)
        loaded = json.loads(reports[0].read_text(encoding="utf-8"))
        assert loaded["gates"]["all_cases_pass"] is True

    @pytest.mark.asyncio
    async def test_report_does_not_leak_private_history(self, tmp_path):
        report = await evaluate_dataset(DATASET)
        raw = json.dumps(report, ensure_ascii=False)
        for s in SAMPLES:
            msg = s["current_message"]
            if len(msg) >= 6:  # 过短消息（如空串/「在吗」）不具私密性
                assert msg not in raw, s["id"]
            for turn in s.get("turns", []):
                content = turn.get("content", "")
                if len(content) >= 8:
                    assert content not in raw, s["id"]


# ═══════════════════════ 二轮上下文接线（丢上下文风险） ═══════════════════════

class TestHistoryWiring:
    @pytest.mark.asyncio
    async def test_followup_plan_carries_prior_turn(self):
        """二轮追问时，上一轮完整问答必须随任务上下文下发且审计计数正确。"""
        from evals.run_stability_regress import new_chat_center, _build_route_context

        sample = SAMPLES_BY_ID["fw-01"]
        cc = new_chat_center()
        plan = await cc.route(message=sample["current_message"], mode="auto",
                              student_profile={},
                              context=_build_route_context(sample))
        task_msgs = plan.tasks[0].context.get("messages") or []
        task_text = json.dumps(task_msgs, ensure_ascii=False)
        for anchor in sample["expected_history_anchors"]:
            assert anchor in task_text, f"任务上下文缺少上一轮锚点: {anchor}"
        assert plan.intent_meta["context_turn_count"] == 2

    @pytest.mark.asyncio
    async def test_normal_chat_creates_single_task_plan(self):
        """普通问答不创建复杂 ExecutionPlan（9.5 计划 Task 4 验收口径）。"""
        from evals.run_stability_regress import new_chat_center, _build_route_context

        cc = new_chat_center()
        for s in SAMPLES:
            if s["category"] == "capability_request" or not s["current_message"].strip():
                continue
            plan = await cc.route(message=s["current_message"], mode="auto",
                                  student_profile={},
                                  context=_build_route_context(s))
            assert len(plan.tasks) == 1, (s["id"], [t.mode for t in plan.tasks])
            assert plan.tasks[0].mode == "auto"


# ═══════════════════════ 无关画像抗扰（ContextBuilder 合同） ═══════════════════════

class TestNoiseProfile:
    def test_irrelevant_profile_facts_not_injected(self):
        """与当前话题零交集的画像字段不得注入；答案塑形字段（风格/基础）保留。"""
        sample = SAMPLES_BY_ID["nr-02"]
        built = ContextBuilder().build(
            system="s",
            current_message=sample["current_message"],
            history=[],
            summary="",
            student_profile=sample["student_profile"],
        )
        facts_text = " | ".join(built.profile_facts)
        for forbidden in sample["profile_facts_forbidden"]:
            assert forbidden not in facts_text, (forbidden, facts_text)
        for required in sample["profile_facts_required"]:
            assert required in facts_text, (required, facts_text)


# ═══════════════════════ 错误终态与异常提示不泄漏（真实执行路径） ═══════════════════════

class _RaisingTutor:
    """模拟 Tutor 底层异常（含敏感细节：配额/key），验证用户可见错误已脱敏。"""

    async def run(self, state):
        raise RuntimeError("HTTP 429: quota exceeded for key sk-test-1234")


class _StubViz:
    async def run(self, question, answer):
        return SimpleNamespace(should_visualize=False, code="", title="",
                               render_type="", warning=None)


def _error_terminal_chat_center() -> ChatCenter:
    return ChatCenter(result_agent=ResultAgent(
        auto_center=AutoCenter(tutor_agent=_RaisingTutor(), visualize_pipeline=_StubViz()),
    ))


class TestErrorTerminalSanitization:
    @pytest.mark.asyncio
    async def test_tutor_exception_surfaces_sanitized_error(self):
        """Agent 异常时：流中必须有 error 事件、仍以 done 终止、异常细节不外泄。"""
        from evals.run_stability_regress import _build_route_context

        sample = SAMPLES_BY_ID["fi-04"]
        cc = _error_terminal_chat_center()
        plan = await cc.route(message=sample["current_message"], mode="auto",
                              student_profile={}, context=_build_route_context(sample))

        events = [ev async for ev in cc.execute(plan)]
        types = [ev.type for ev in events]
        assert StreamEventType.ERROR in types, [t.value for t in types]
        assert types[-1] is StreamEventType.DONE, [t.value for t in types]

        blob = json.dumps(
            [{"type": ev.type.value, "message": ev.message, "data": ev.data} for ev in events],
            ensure_ascii=False, default=str,
        )
        for marker in ("sk-test-1234", "RuntimeError", "429", "Traceback"):
            assert marker not in blob, f"异常细节泄漏: {marker}"


# ═══════════════════════ 普通聊天端到端（mock Tutor，真实编排接线） ═══════════════════════

class _EmptyKB:
    def is_empty(self):
        return True

    def search(self, *args, **kwargs):
        return []


async def _no_knowledge_nodes(**kwargs):
    return {"primary": [], "related": [], "broad": [], "all": []}


def _mock_tutor_chat_center() -> ChatCenter:
    return ChatCenter(result_agent=ResultAgent(
        auto_center=AutoCenter(tutor_agent=TutorAgent(use_mock_llm=True),
                               visualize_pipeline=_StubViz()),
    ))


class TestNormalChatE2E:
    @pytest.mark.asyncio
    async def test_normal_chat_reaches_tutor_with_content_and_done(self, monkeypatch):
        """普通聊天全链路：route(auto) → AutoCenter → TutorAgent → content + done。

        同时覆盖 conversation_id 向 Tutor state 的透传，避免正常答疑在编排层降级为 error。
        """
        monkeypatch.setattr("app.agents.tutor_agent.get_kb", lambda: _EmptyKB())
        monkeypatch.setattr("app.services.knowledge_base.get_kb", lambda: _EmptyKB())
        monkeypatch.setattr(result_agent_module, "extract_knowledge_nodes", _no_knowledge_nodes)

        from evals.run_stability_regress import _build_route_context

        sample = SAMPLES_BY_ID["cq-01"]
        cc = _mock_tutor_chat_center()
        plan = await cc.route(message=sample["current_message"], mode="auto",
                              student_profile={}, context=_build_route_context(sample))

        content_parts: list[str] = []
        error_events: list[str] = []
        terminal = None
        async for ev in cc.execute(plan):
            if ev.type is StreamEventType.CONTENT:
                data = ev.data
                if isinstance(data, dict):
                    piece = data.get("response") or data.get("content") or ""
                    if isinstance(piece, str):
                        content_parts.append(piece)
                elif isinstance(data, str):
                    content_parts.append(data)
            elif ev.type is StreamEventType.ERROR:
                error_events.append(str(ev.message))
            elif ev.type in (StreamEventType.DONE, StreamEventType.INQUIRY):
                terminal = ev.type

        assert not error_events, f"普通聊天出现错误事件: {error_events}"
        assert terminal is StreamEventType.DONE, terminal
        assert "".join(content_parts).strip(), "普通聊天必须产出非空回答内容"
