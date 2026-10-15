"""路由观测日志（对话底座救援 · Task 5）。

每次聊天请求在 ChatCenter 边界产出一条结构化、脱敏的 JSON 日志，
供误触发审计与后续评测门禁（Task 10）关联分析。

脱敏红线（与诊断文档"观测字段"一致）：
- 只允许白名单字段；
- 不记录 student_profile 的任何值（Task 6 起只记字段名 profile_fields_used）；
- 不记录历史消息、当前消息或回答正文；
- 不记录密钥与完整私密对话。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

AUDIT_LOGGER = "routing.audit"

_logger = logging.getLogger(AUDIT_LOGGER)

# 白名单字段：日志记录里不允许出现除此之外的任何键
ALLOWED_KEYS = frozenset({
    "ts",              # UTC ISO-8601
    "trace_id",        # 请求追踪 ID（透传；缺失时自动生成）
    "conversation_id", # Java 会话 ID
    "route",           # NORMAL_CHAT / PLAN / RESOURCE / EXERCISE / VISUALIZATION
    "route_reason",    # 路由依据（capability_evidence:* / no_capability_evidence / explicit_mode:* 等）
    "route_source",    # T4-A：rule（规则直通）/ semantic（语义重判）/ fallback（兜底）
    "semantic_state",  # T4-A：direct_capability / direct_chat / uncertain
    "semantic_called", # T4-A：本次是否真正调用了语义判定（bool）
    "semantic_latency_ms", # T4-A：语义判定耗时（未调用为 None）
    "semantic_error",  # T4-A：语义判定错误类别（timeout / 异常类型 / None）
    "context_turn_count",  # 本次请求携带的历史消息条数（数字，不含正文）
    "profile_fields_used", # Task 6 ContextBuilder 起填充；当前为 None
    "kb_chunks_used",      # Task 6 起填充；当前为 None
    "model_latency_ms",    # ChatTaskDispatcher 管线耗时（原 ResultAgent）
    "retry_count",         # Task 8 ResponseSanityCheck 起有意义；当前恒 0
    "sse_terminal_event",  # done / error / None（管线视角的终止事件）
    "error_code",          # Task 3/8 定义错误码后填充；当前为 None
})


def new_trace_id() -> str:
    """未透传 trace_id 时生成短随机 ID，保证日志可关联。"""
    return uuid.uuid4().hex[:12]


def build_routing_record(
    *,
    trace_id: str,
    conversation_id: Any,
    route: str,
    route_reason: str,
    context_turn_count: int,
    model_latency_ms: float,
    retry_count: int = 0,
    sse_terminal_event: str | None = None,
    profile_fields_used: list | None = None,
    kb_chunks_used: list | None = None,
    error_code: str | None = None,
    route_source: str | None = None,
    semantic_state: str | None = None,
    semantic_called: bool | None = None,
    semantic_latency_ms: float | None = None,
    semantic_error: str | None = None,
) -> dict:
    """构建一条脱敏路由记录。白名单之外的键一律丢弃。"""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "route": route,
        "route_reason": route_reason,
        "route_source": route_source,
        "semantic_state": semantic_state,
        "semantic_called": semantic_called,
        "semantic_latency_ms": (
            round(semantic_latency_ms, 2) if semantic_latency_ms is not None else None
        ),
        "semantic_error": semantic_error,
        "context_turn_count": context_turn_count,
        "profile_fields_used": profile_fields_used,
        "kb_chunks_used": kb_chunks_used,
        "model_latency_ms": round(model_latency_ms, 2),
        "retry_count": retry_count,
        "sse_terminal_event": sse_terminal_event,
        "error_code": error_code,
    }
    return {k: v for k, v in record.items() if k in ALLOWED_KEYS}


def emit_routing_record(record: dict) -> None:
    """以单行 JSON 输出路由记录；任何序列化异常都不能打断聊天流。"""
    try:
        _logger.info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:  # pragma: no cover - 日志失败不影响主流程
        _logger.debug("routing audit emit failed", exc_info=True)
