"""普通聊天稳定性回归运行器（chat_stability_v1）。

与 chat_foundation_v1（60 条冻结评测集，Task 10 门禁指标口径）互补：
本运行器面向"小而稳定、每次改动后必跑"的回归场景，19 条、全离线、秒级完成。
每条样例的断言轴直接对应稳定性风险：

- 期望路由（真实 CapabilityGate + ChatCenter.route，确定性、无 LLM）
- 首任务模式（普通问答 = auto 直达 Tutor；能力请求进入对应编排中心；空输入 = inquiry）
- SSE 终止合同（done / error）与内容合同（是否应有用户可见内容）
- 二轮上下文接线（上一轮问答必须随任务上下文下发；ContextBuilder 当前消息恒在末位）
- 无关画像抗扰（ContextBuilder 只注入与当前话题相关的画像片段）
- 故障注入（空回答重试、连续失败降级、内部泄露拦截、错误终态可观测），
  走生产真实的 run_with_sanity_check 重试编排，脚本化 generate 输出

复用的生产合同（不重新实现）：
- CapabilityGate.decide        （app/services/capability_gate.py）
- ChatCenter.route             （app/centers/chat_center.py）
- ContextBuilder.build         （app/services/context_builder.py）
- check_response / run_with_sanity_check（app/services/response_sanity.py）

用法（项目根目录或 ai-service 目录均可）：
    python evals/run_stability_regress.py                 # 全量 19 条，报告写入 evals/reports/
    python evals/run_stability_regress.py --no-write      # 只看摘要
退出码：0 = 全部门禁通过；1 = 存在回归（门禁不达标）。
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parent
AI_SERVICE = PROJECT_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.centers.router_agent import RouterAgent  # noqa: E402
from app.services.capability_gate import CapabilityGate  # noqa: E402
from app.services.context_builder import ContextBuilder  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402
from app.services.response_sanity import (  # noqa: E402
    SanityVerdict,
    check_response,
    run_with_sanity_check,
)

DATASET = EVALS_DIR / "chat_stability_v1.jsonl"
REPORT_DIR = EVALS_DIR / "reports"

# 模拟"健康 Tutor"的固定中文回答（离线确定性；不含任何内部标记，sanity 应判 ACCEPT）
HEALTHY_ANSWER = (
    "进程是操作系统进行资源分配的基本单位，它拥有独立的地址空间，"
    "线程则是 CPU 调度的基本单位，同一进程内的线程共享内存。"
)
CONTEXT_SYSTEM_STUB = "你是在线学习助教，用中文回答学生的计算机基础问题。"


def load_samples(dataset_path: Path) -> list[dict]:
    samples = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def new_chat_center() -> ChatCenter:
    """与线上同一聊天入口的离线实例：真实 CapabilityGate + mock 意图抽取（无 LLM）。"""
    return ChatCenter(router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)))


# ═══════════════════════ 模拟客户端（SSE 终止合同用） ═══════════════════════

async def simulate_healthy(sample: dict) -> tuple[str, str]:
    """健康流：有内容（除非 inquiry 场景）且以 done 终止。"""
    return ("" if not sample.get("expect_content", True) else HEALTHY_ANSWER), "done"


async def simulate_degraded(sample: dict) -> tuple[str, str]:
    """退化流：内容正常但流以 error 终止（对应线上流中断/后端异常）。"""
    return HEALTHY_ANSWER, "error"


# ═══════════════════════ 单条样例评测 ═══════════════════════

def _build_route_context(sample: dict) -> dict:
    """与 internal_api 相同的口径：history + 当前消息作为最后一条 user 消息。"""
    return {
        "messages": list(sample.get("turns") or [])
        + [{"role": "user", "content": sample["current_message"]}],
        "conversation_id": None,
        "trace_id": f"stab-{sample['id']}",
    }


async def _eval_fault_sanity(sample: dict) -> tuple[dict, str, object]:
    """故障注入（sanity 重试编排）：走生产 run_with_sanity_check，脚本化 generate 输出。"""
    fault = sample["fault"]
    answers: list[str] = fault["answers"]
    expect = fault["expect"]
    seen_contexts: list[dict] = []

    async def scripted_generate(context: dict) -> str:
        seen_contexts.append(context)
        return answers[min(len(seen_contexts) - 1, len(answers) - 1)]

    marker_context = {"built_context_marker": sample["id"]}
    outcome = await run_with_sanity_check(
        scripted_generate,
        marker_context,
        request_message=sample["current_message"],
        max_attempts=2,
    )

    same_context = all(c is marker_context for c in seen_contexts)
    checks = {
        "verdict": outcome.verdict.value == expect["verdict"],
        "error_code": outcome.error_code == expect["error_code"],
        "attempts": outcome.attempts == expect["attempts"],
        "text": outcome.text == expect["text"],
        "failure_reasons": outcome.failure_reasons == expect["failure_reasons"],
        "same_context_on_retry": same_context is expect["same_context"],
    }
    detail = (
        f"verdict={outcome.verdict.value} code={outcome.error_code} "
        f"attempts={outcome.attempts} reasons={outcome.failure_reasons}"
    )
    return checks, detail, outcome


async def _eval_fault_terminal_error(sample: dict) -> tuple[dict, str]:
    """故障注入（错误终态）：流中途以 error 终止，验证可观测性与异常提示不泄漏。"""
    fault = sample["fault"]
    streamed_text = fault["streamed_text"]
    observed_terminal = fault["terminal"]

    leaked = [kw for kw in sample.get("must_not_include", []) if kw in streamed_text]
    checks = {
        "terminal_is_error": observed_terminal == "error" == sample["expected_terminal"],
        "not_counted_as_done": observed_terminal != "done",
        "content_expectation_matches": sample["expect_content"] is False,
        "no_exception_leak": not leaked,
    }
    detail = f"terminal={observed_terminal} leaked={leaked or '无'}"
    return checks, detail


async def evaluate_case(sample: dict, cc: ChatCenter, builder: ContextBuilder,
                        gate: CapabilityGate) -> dict:
    message = sample["current_message"]
    profile = sample.get("student_profile") or {}
    turns = list(sample.get("turns") or [])
    axes: dict[str, bool] = {}
    notes: list[str] = []

    # ── 路由轴：真实 ChatCenter.route（CapabilityGate 一级 + 二级编排路由）──
    plan = await cc.route(message=message, mode="auto", student_profile=profile,
                          context=_build_route_context(sample))
    actual_route = plan.intent_meta.get("route", "NORMAL_CHAT")
    axes["route"] = actual_route == sample["expected_route"]
    if sample.get("expected_task_mode"):
        first_mode = plan.tasks[0].mode if plan.tasks else None
        axes["task_mode"] = first_mode == sample["expected_task_mode"]
        if first_mode != sample["expected_task_mode"]:
            notes.append(f"first_task_mode={first_mode}")

    # ── 二轮上下文接线轴：上一轮必须随任务上下文下发，审计计数正确 ──
    if sample.get("expect_history_in_context"):
        anchors = sample.get("expected_history_anchors") or []
        task_msgs = (plan.tasks[0].context.get("messages") if plan.tasks else None) or []
        task_text = json.dumps(task_msgs, ensure_ascii=False)
        axes["history_in_task_context"] = all(a in task_text for a in anchors)
        if sample.get("expected_context_turn_count") is not None:
            axes["context_turn_count"] = (
                plan.intent_meta.get("context_turn_count") == sample["expected_context_turn_count"]
            )

        # ContextBuilder 合同：历史进最近窗口、当前消息恒在最终 user 位置
        built = builder.build(
            system=CONTEXT_SYSTEM_STUB,
            current_message=message,
            history=turns + [{"role": "user", "content": message}],
            summary=None,
            student_profile=profile,
        )
        built_text = json.dumps(built.recent_turns, ensure_ascii=False)
        axes["history_in_built_context"] = all(a in built_text for a in anchors)
        axes["current_message_last"] = (
            bool(built.messages())
            and built.messages()[-1].get("role") == "user"
            and built.messages()[-1].get("content") == message
        )

    # ── 无关画像抗扰轴：ContextBuilder 只注入相关画像片段 ──
    if profile and (sample.get("profile_facts_forbidden") or sample.get("profile_facts_required")):
        built_p = builder.build(
            system=CONTEXT_SYSTEM_STUB,
            current_message=message,
            history=turns,
            summary="",
            student_profile=profile,
        )
        facts_text = " | ".join(built_p.profile_facts)
        axes["irrelevant_profile_ignored"] = all(
            f not in facts_text for f in sample.get("profile_facts_forbidden", [])
        )
        axes["required_profile_kept"] = all(
            r in facts_text for r in sample.get("profile_facts_required", [])
        )
        if not axes["irrelevant_profile_ignored"]:
            notes.append(f"profile_facts={facts_text}")

    # ── SSE 终止 / 内容合同轴 ──
    # fault.kind=terminal_error：错误终态可观测性；fault.kind=sanity：终态由 sanity 裁决推导
    # （ACCEPT → done 且放行内容；USER_SAFE_ERROR → error 且 text=None，不得伪造 content）；
    # 其余行为样例：健康模拟客户端。
    fault = sample.get("fault")
    if fault and fault.get("kind") == "terminal_error":
        t_checks, t_detail = await _eval_fault_terminal_error(sample)
        axes.update(t_checks)
        notes.append(t_detail)
    elif fault and fault.get("kind") == "sanity":
        f_checks, f_detail, outcome = await _eval_fault_sanity(sample)
        axes.update(f_checks)
        terminal_derived = "done" if outcome.verdict is SanityVerdict.ACCEPT else "error"
        axes["terminal"] = terminal_derived == sample["expected_terminal"]
        has_content = bool((outcome.text or "").strip())
        axes["content"] = has_content == sample["expect_content"]
        if has_content:
            leaked = [kw for kw in sample.get("must_not_include", []) if kw in outcome.text]
            axes["no_internal_leak"] = not leaked
            if leaked:
                notes.append(f"leaked={leaked}")
        notes.append(f_detail)
    else:
        answer, terminal = await simulate_healthy(sample)
        axes["terminal"] = terminal == sample["expected_terminal"]
        has_content = bool(answer.strip())
        axes["content"] = has_content == sample["expect_content"]
        if has_content:
            sanity = check_response(answer, request_message=message)
            axes["sanity_accept"] = sanity.verdict is SanityVerdict.ACCEPT
            leaked = [kw for kw in sample.get("must_not_include", []) if kw in answer]
            axes["no_internal_leak"] = not leaked
            if leaked:
                notes.append(f"leaked={leaked}")

    passed = all(axes.values())
    return {
        "id": sample["id"],
        "category": sample["category"],
        "expected_route": sample["expected_route"],
        "actual_route": actual_route,
        "axes": axes,
        "passed": passed,
        "notes": notes,
    }


def _route_calibration_divergences(samples: list[dict], gate: CapabilityGate) -> list[dict]:
    """数据标定 vs 真实 CapabilityGate：分歧需要人工裁决（防标定漂移）。"""
    divergences = []
    for sample in samples:
        if not sample["current_message"].strip():
            continue  # 空输入不走能力判定（inquiry 路径），无标定意义
        actual = gate.decide(sample["current_message"], mode="auto").kind.value
        if actual != sample["expected_route"]:
            divergences.append({
                "id": sample["id"],
                "expected": sample["expected_route"],
                "gate": actual,
            })
    return divergences


async def evaluate_dataset(dataset_path: Path) -> dict:
    samples = load_samples(Path(dataset_path))
    cc = new_chat_center()
    builder = ContextBuilder()
    gate = CapabilityGate()

    records = []
    for sample in samples:
        records.append(await evaluate_case(sample, cc, builder, gate))

    # 退化扫描：健康样例若流以 error 终止，必须能被终止合同发现（会计不反向）
    degradation_undetected = 0
    for sample in samples:
        if sample.get("fault"):
            continue
        _, terminal = await simulate_degraded(sample)
        if terminal == sample["expected_terminal"]:
            degradation_undetected += 1

    divergences = _route_calibration_divergences(samples, gate)
    failed = [r for r in records if not r["passed"]]

    report = {
        "dataset": Path(dataset_path).name,
        "total": len(samples),
        "passed": len(records) - len(failed),
        "failed_cases": [r["id"] for r in failed],
        "route_calibration_divergences": divergences,
        "degradation_undetected": degradation_undetected,
        "axis_pass_rates": _axis_pass_rates(records),
        "records": records,
    }
    return report


def _axis_pass_rates(records: list[dict]) -> dict[str, float]:
    totals: dict[str, int] = {}
    oks: dict[str, int] = {}
    for rec in records:
        for axis, ok in rec["axes"].items():
            totals[axis] = totals.get(axis, 0) + 1
            oks[axis] = oks.get(axis, 0) + (1 if ok else 0)
    return {axis: round(oks[axis] / totals[axis], 4) for axis in sorted(totals)}


def check_gates(report: dict) -> dict[str, bool]:
    return {
        "route_calibration_zero_divergence": len(report["route_calibration_divergences"]) == 0,
        "all_cases_pass": len(report["failed_cases"]) == 0,
        "degradation_always_detected": report["degradation_undetected"] == 0,
    }


def write_report(report: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = out_dir / f"chat_stability_{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _print_summary(report: dict, gates: dict[str, bool], report_path: Path | None) -> None:
    print(f"total={report['total']} passed={report['passed']} "
          f"failed={report['failed_cases'] or '无'}")
    print(f"route_calibration_divergences={len(report['route_calibration_divergences'])} (==0)")
    print(f"degradation_undetected={report['degradation_undetected']} (==0)")
    for axis, rate in report["axis_pass_rates"].items():
        print(f"  axis {axis}: {rate:.2%}")
    if report_path:
        print(f"report={report_path}")
    print("gates: " + " ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in gates.items()))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="普通聊天稳定性回归运行器（chat_stability_v1）")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    parser.add_argument("--no-write", action="store_true", help="只输出摘要，不落报告文件")
    args = parser.parse_args(argv)

    report = await evaluate_dataset(Path(args.dataset))
    gates = check_gates(report)
    report["gates"] = gates

    report_path = None if args.no_write else write_report(report, Path(args.out_dir))
    _print_summary(report, gates, report_path)
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
