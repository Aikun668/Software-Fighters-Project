"""评测运行器与回归门禁（对话底座救援 · Task 10）。

绕开页面，直接调用同一个聊天入口（ChatCenter.route）跑评测集：
- 一级路由结果来自真实 CapabilityGate（确定性、无 LLM、离线可复跑）；
- 回答与终止事件由可注入的客户端产出：默认 FakeEvalClient（离线确定性），
  fault-injection 用 BrokenEvalClient（恒以 error 终止）验证门禁会拦；
  真实 LLM 客户端在 Task 11 解冻评审时接入（实现同样的 run() 协议即可）。
- 每条记录：route、终止事件、输出摘要（≤120 字）、机器断言结果、人工复核标记；
  不写 current_message / turns 正文（不落完整私密历史）。

门禁（不达标非零退出）：
- 能力误触发率 ≤ 5%
- 明确能力请求识别率 ≥ 90%
- SSE done 率 ≥ 99%
- 空/重复/截断/内部泄露 = 0

用法（项目根目录）：
    python evals/run_chat_eval.py                       # 默认 fake 客户端，产出报告
    python evals/run_chat_eval.py --client broken       # 注入 SSE 退化，验证门禁拦截
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parent
AI_SERVICE = PROJECT_ROOT / "ai-service"
sys.path.insert(0, str(AI_SERVICE))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(AI_SERVICE / ".env")

# 评测域模型覆盖（须在导入 app.* 之前生效）：
# .env 把聊天通道配成 deepseek-v4-flash——官方 API 上这是思考模型，
# reasoning_content 先行、content 常为空（llm_service 不读 reasoning_content）。
# 评测统一用非思考别名 deepseek-chat；要沿用 .env 原配置设 EVAL_RESPECT_LLM_ENV=1。
if os.environ.get("EVAL_RESPECT_LLM_ENV", "") != "1":
    os.environ["DEEPSEEK_MODEL_CHAT"] = os.environ.get("EVAL_LLM_MODEL_CHAT", "deepseek-chat")
    os.environ["DEEPSEEK_MODEL_REASONER"] = os.environ.get("EVAL_LLM_MODEL_REASONER", "deepseek-chat")

from app.centers.chat_center import ChatCenter  # noqa: E402
from app.centers.router_agent import RouterAgent  # noqa: E402
from app.services.capability_gate import CapabilityKind  # noqa: E402
from app.services.intent_extractor import IntentExtractor  # noqa: E402
from app.services.response_sanity import SanityVerdict, check_response  # noqa: E402

CAPABILITY_ROUTES = {"PLAN", "RESOURCE", "EXERCISE", "VISUALIZATION"}
# CapabilityKind → 编排中心（ResultAgent 的 task.mode）
ROUTE_TO_CENTER = {
    "PLAN": "plan",
    "RESOURCE": "resource",
    "EXERCISE": "exercise",
    "VISUALIZATION": "visualization",
}
EXCERPT_LIMIT = 120
TERMINAL_EVENTS = ("done", "error", "inquiry", "timeout")

GATES = {
    "capability_false_trigger_rate": lambda r: r <= 0.05,
    "capability_recognition_rate": lambda r: r >= 0.90,
    "sse_done_rate": lambda r: r >= 0.99,
    "normal_sse_done_rate": lambda r: r >= 0.99,  # rubric 口径：done 率按普通问答计
    "sanity_violations": lambda r: r == 0,
}


def load_samples(dataset_path: Path) -> list[dict]:
    samples = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


class FakeEvalClient:
    """离线确定性假客户端：固定合法中文回答，SSE 恒以 done 终止。

    路由指标仍然真实（来自真实 CapabilityGate）；回答类断言（must_include）
    离线不可验证，失败条目进入人工复核列表，由真实运行裁决。
    """

    CANNED_ANSWER = (
        "这是离线评测的固定回答：进程是资源分配的基本单位，"
        "线程共享进程资源，TCP 三次握手用于确认双向可达。"
    )

    async def run(self, sample: dict, plan, chat_center: ChatCenter) -> tuple[str, str]:
        return self.CANNED_ANSWER, "done"


class BrokenEvalClient:
    """故障注入客户端：回答正常但流以 error 终止，用于验证门禁拦截。"""

    async def run(self, sample: dict, plan, chat_center: ChatCenter) -> tuple[str, str]:
        return "这是一个用于门禁测试的正常回答内容。", "error"


class LiveEvalClient:
    """真实客户端：执行真实管线（ChatCenter.execute），汇聚 content，捕获终止事件。

    超时按 terminal="timeout" 记录（等同于生产中的流中断），不伪装成 done。
    """

    def __init__(self, normal_timeout: float = 120.0, capability_timeout: float = 420.0):
        self.normal_timeout = normal_timeout
        self.capability_timeout = capability_timeout

    async def run(self, sample: dict, plan, chat_center: ChatCenter) -> tuple[str, str]:
        timeout = (
            self.capability_timeout
            if sample.get("expected_route") in CAPABILITY_ROUTES
            else self.normal_timeout
        )
        parts: list[str] = []
        terminal: str | None = None

        async def consume() -> None:
            nonlocal terminal
            async for event in chat_center.execute(plan):
                if event.type.value == "content":
                    data = event.data
                    if isinstance(data, str):
                        parts.append(data)
                    elif isinstance(data, dict):
                        piece = data.get("response") or data.get("content") or ""
                        if isinstance(piece, str):
                            parts.append(piece)
                elif event.type.value in ("done", "error", "inquiry"):
                    terminal = event.type.value

        try:
            await asyncio.wait_for(consume(), timeout=timeout)
        except asyncio.TimeoutError:
            terminal = "timeout"
        except Exception:
            terminal = "error"
        return "".join(parts), terminal or "error"


CLIENTS = {"fake": FakeEvalClient, "broken": BrokenEvalClient, "live": LiveEvalClient}


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text[:EXCERPT_LIMIT] + ("…" if len(text) > EXCERPT_LIMIT else "")


def _new_chat_center() -> ChatCenter:
    return ChatCenter(
        router_agent=RouterAgent(intent_extractor=IntentExtractor(use_mock=True)),
    )


async def evaluate_dataset(
    dataset_path: Path,
    client=None,
    chat_center: ChatCenter | None = None,
    collect_answers: bool = False,
) -> dict:
    """跑完整评测集，返回聚合报告（含逐条 records）。

    collect_answers=True 时额外携带 _full_answers（id -> 全量回答），
    仅供抽检评分；write_report 会将其剥离到独立的 live_answers 文件。
    """
    client = client or FakeEvalClient()
    cc = chat_center or _new_chat_center()
    samples = load_samples(Path(dataset_path))
    full_answers: dict[str, dict] = {}

    records: list[dict] = []
    normal_total = capability_total = 0
    normal_done = global_done = 0
    false_triggers = capability_hits = 0
    sanity_failures: dict[str, int] = {}
    needs_review: list[dict] = []

    for sample in samples:
        expected = sample["expected_route"]
        message = sample["current_message"]

        plan = await cc.route(
            message=message,
            mode="auto",
            student_profile={},
            context={
                # rubric 执行口径：turns 作为历史，current_message 作为最后一条用户消息
                "messages": list(sample.get("turns") or []) + [
                    {"role": "user", "content": message}
                ],
                "conversation_id": None,
                "trace_id": f"eval-{sample['id']}",
            },
        )
        actual = plan.intent_meta.get("route", CapabilityKind.NORMAL_CHAT.value)
        route_correct = actual == expected
        first_task_mode = plan.tasks[0].mode if plan.tasks else None
        orchestration_entered = (
            expected in ROUTE_TO_CENTER and first_task_mode == ROUTE_TO_CENTER[expected]
        )

        answer, terminal = await client.run(sample, plan, cc)
        print(f"[{len(records) + 1}/{len(samples)}] {sample['id']} route={actual} "
              f"terminal={terminal} len={len(answer)}", flush=True)
        if collect_answers:
            full_answers[sample["id"]] = {"answer": answer, "terminal": terminal}
        sanity = check_response(answer, request_message=message)

        if terminal == "done":
            global_done += 1
            if expected == "NORMAL_CHAT":
                normal_done += 1

        if expected == "NORMAL_CHAT":
            normal_total += 1
            if actual in CAPABILITY_ROUTES:
                false_triggers += 1
        elif expected in CAPABILITY_ROUTES:
            capability_total += 1
            if actual == expected:
                capability_hits += 1

        if sanity.verdict is not SanityVerdict.ACCEPT:
            sanity_failures[sanity.reason] = sanity_failures.get(sanity.reason, 0) + 1

        must_include_missing = [
            kw for kw in sample.get("must_include", []) if kw not in answer
        ]
        must_not_include_violated = [
            kw for kw in sample.get("must_not_include", []) if kw in answer
        ]
        machine_checks = {
            "route": route_correct,
            "sse_done": terminal == "done",
            "orchestration_entered": orchestration_entered,
            "must_include": must_include_missing,
            "must_not_include": must_not_include_violated,
            "sanity": sanity.reason if sanity.verdict is not SanityVerdict.ACCEPT else None,
        }

        review_reasons = []
        if not route_correct:
            review_reasons.append("route_mismatch")
        if expected in CAPABILITY_ROUTES and not orchestration_entered:
            review_reasons.append("orchestration_not_entered")
        if must_include_missing:
            review_reasons.append("must_include_unverified_or_failed")
        if must_not_include_violated:
            review_reasons.append("must_not_include_violated")
        if sanity.verdict is not SanityVerdict.ACCEPT:
            review_reasons.append(f"sanity:{sanity.reason}")
        if terminal != "done":
            review_reasons.append(f"terminal_{terminal}")
        if review_reasons:
            needs_review.append({"id": sample["id"], "reason": ";".join(review_reasons)})

        records.append({
            "id": sample["id"],
            "category": sample["category"],
            "expected_route": expected,
            "actual_route": actual,
            "route_correct": route_correct,
            "first_task_mode": first_task_mode,
            "terminal_event": terminal,
            "sanity_verdict": sanity.verdict.value,
            "sanity_reason": sanity.reason if sanity.verdict is not SanityVerdict.ACCEPT else None,
            "machine_checks": machine_checks,
            "output_excerpt": _excerpt(answer),
            "needs_review": bool(review_reasons),
        })

    total = len(samples)
    report = {
        "dataset": Path(dataset_path).name,
        "client": type(client).__name__,
        "llm_model_chat": os.environ.get("DEEPSEEK_MODEL_CHAT", ""),
        "total": total,
        "capability_false_trigger_rate": round(false_triggers / normal_total, 4) if normal_total else 0.0,
        "capability_recognition_rate": round(capability_hits / capability_total, 4) if capability_total else 0.0,
        "sse_done_rate": round(global_done / total, 4) if total else 0.0,
        "normal_sse_done_rate": round(normal_done / normal_total, 4) if normal_total else 0.0,
        "sanity_violations": sum(sanity_failures.values()),
        "sanity_breakdown": sanity_failures,
        "route_mismatches": sum(1 for r in records if not r["route_correct"]),
        "needs_review": needs_review,
        "records": records,
    }
    if collect_answers:
        report["_full_answers"] = full_answers
    return report


def check_gates(report: dict) -> dict[str, bool]:
    return {
        name: GATES[name](report.get(name, 0))
        for name in GATES
    }


def write_report(report: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = out_dir / f"chat_foundation_{stamp}.json"
    payload = dict(report)
    answers = payload.pop("_full_answers", None)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 全量回答单独落盘，仅供 Task 11 抽检评分；不进入正式报告
    if answers is not None:
        answers_path = out_dir / f"live_answers_{stamp}.json"
        answers_path.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"answers={answers_path}")
    return path


def _print_summary(report: dict, gates: dict[str, bool], report_path: Path | None) -> None:
    print(f"total={report['total']} client={report['client']} llm_model={report.get('llm_model_chat', '-')}")
    print(f"capability_false_trigger_rate={report['capability_false_trigger_rate']:.4f} (≤0.05)")
    print(f"capability_recognition_rate={report['capability_recognition_rate']:.4f} (≥0.90)")
    print(f"sse_done_rate={report['sse_done_rate']:.4f} (≥0.99) normal={report['normal_sse_done_rate']:.4f}")
    print(f"sanity_violations={report['sanity_violations']} (==0) {report['sanity_breakdown']}")
    print(f"route_mismatches={report['route_mismatches']} needs_review={len(report['needs_review'])}")
    if report_path:
        print(f"report={report_path}")
    print("gates: " + " ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in gates.items()))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对话底座评测运行器（Task 10/11）")
    parser.add_argument("--dataset", default=str(EVALS_DIR / "chat_foundation_v1.jsonl"))
    parser.add_argument("--out-dir", default=str(EVALS_DIR / "reports"))
    parser.add_argument("--client", choices=sorted(CLIENTS), default="fake")
    parser.add_argument("--no-write", action="store_true", help="只输出摘要，不落报告文件")
    parser.add_argument("--collect-answers", action="store_true",
                        help="额外落盘全量回答（live_answers_*.json，供抽检评分）")
    args = parser.parse_args(argv)

    client = CLIENTS[args.client]()
    report = await evaluate_dataset(Path(args.dataset), client=client,
                                    collect_answers=args.collect_answers)
    gates = check_gates(report)
    report["gates"] = gates

    report_path = None
    if not args.no_write:
        report_path = write_report(report, Path(args.out_dir))

    _print_summary(report, gates, report_path)
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
