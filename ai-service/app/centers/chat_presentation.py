"""聊天呈现层：把 Center 产物转成「用户可见正文」与 SSE 帧的纯函数。

【T5 职责收敛】这些函数原属 `ChatTaskDispatcher`（`chat_task_dispatcher.py`），
是「业务正文合成 / SSE 帧拼装」，与"任务调度"职责无关。T5-Gate ② 要求
Dispatcher 不再混业务正文合成，故抽到本模块。

【零行为变化】函数逻辑逐字搬移，Dispatcher 只调用不持有。对外 SSE 契约由
`sse_contract.json`（sha256 866a6c6d）钉死，并有
`tests/test_t5_sse_contract_baseline.py` 的 `--verify` 自动守线。

纯函数：无实例状态、无 IO、无 LLM 调用。
"""

from app.centers.schemas import AggregatedResult, CenterResult
from app.events.types import StreamEventType


def ensure_user_visible_response(result: CenterResult) -> dict:
    """统一 content 合同（Task 11 评审回归项）：前端与 internal_api 的正文
    只从 payload 的 response/content 键提取。中心产物 payload 若两者皆无，
    优先取真实产物文本（solve 的 solution），仍无才合成用户可读摘要
    （cap-01/05/06）。合不出摘要时保持 payload 原样，空正文由
    internal_api 的终态合同转成 error，而不是伪造 content。"""
    payload = result.payload if isinstance(result.payload, dict) else {}
    if payload.get("response") or payload.get("content"):
        return payload
    solution = payload.get("solution")
    if isinstance(solution, str) and solution.strip():
        return {**payload, "response": solution, "content": solution}
    summary = summarize_product(result.mode, payload)
    if not summary:
        return payload
    return {**payload, "response": summary, "content": summary}


def summarize_product(mode: str, payload: dict) -> str:
    title = str(payload.get("title") or payload.get("topic") or "").strip()
    quoted = f"「{title}」" if title else ""
    if mode == "plan":
        steps = payload.get("steps") or []
        total = payload.get("total_steps") or len(steps)
        text = f"已为你生成{quoted}学习计划，共 {total} 步"
        names = []
        for step in steps[:3]:
            if isinstance(step, dict):
                name = step.get("title") or step.get("topic") or step.get("name")
                if name:
                    names.append(str(name))
        if names:
            text += "：" + "；".join(names)
        days = payload.get("estimated_days")
        if days:
            text += f"，预计 {days} 天完成"
        return text + "。"
    if mode == "visualization":
        blocks = payload.get("blocks") or []
        return f"已为你生成{quoted}的可视化图解，共 {len(blocks)} 个内容块。"
    if mode == "exercise":
        count = payload.get("count") or payload.get("total")
        return f"已为你生成{quoted}的 {count} 道练习题。" if count else f"已为你生成{quoted}练习题。"
    if mode == "resource":
        return f"已为你生成{quoted}的学习资源。"
    # 无可描述产物（如 auto 中心空回答）时返回空串：由上层终态合同
    # 补 error，而不是伪造「已完成xx处理。」
    return ""


def map_event_type(event_type: str) -> StreamEventType:
    mapping = {
        "content": StreamEventType.CONTENT,
        "plan": StreamEventType.CONTENT,
        "resource": StreamEventType.CONTENT,
        "exercise": StreamEventType.CONTENT,
        "visualization": StreamEventType.CONTENT,
        "error": StreamEventType.ERROR,
        "inquiry": StreamEventType.INQUIRY,
    }
    return mapping.get(event_type, StreamEventType.CONTENT)


def build_run_summary(aggregated: AggregatedResult) -> str:
    if not aggregated.results:
        return "已完成处理。"
    parts = []
    for r in aggregated.results:
        if r.error:
            parts.append(f"{r.mode} 执行出现错误")
        else:
            parts.append(f"{r.mode} 已完成")
    return "；".join(parts) + "。"


def build_next_steps(aggregated: AggregatedResult) -> list[str]:
    steps = []
    intents = [r.intent for r in aggregated.results if not r.error]
    if "learning_path" in intents and "exercise_gen" not in intents:
        steps.append("可以尝试生成配套练习题巩固路径内容")
    if "exercise_gen" in intents and "learning_path" not in intents:
        steps.append("可以规划系统学习路径")
    if "resource_gen" in intents:
        steps.append("可以导出为 PPT/PDF 便于复习")
    return steps
