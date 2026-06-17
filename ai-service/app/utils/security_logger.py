"""Structured security event logging for monitoring and alerting."""

import logging
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

EventType = Literal[
    "input_violation",
    "output_flagged",
    "hallucination_warning",
    "pipeline_error",
]
Severity = Literal["low", "medium", "high", "critical"]


class SecurityLogger:

    @staticmethod
    def log_event(
        event_type: EventType,
        details: dict,
        *,
        severity: Severity = "medium",
    ):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "user_id": details.get("user_id"),
            "agent": details.get("agent"),
            "content_preview": (details.get("content", "") or "")[:50],
            "extra": details.get("extra", {}),
        }
        if event_type in ("input_violation", "pipeline_error"):
            logger.warning("security_event | %s", _fmt(entry))
        else:
            logger.info("security_event | %s", _fmt(entry))


def _fmt(entry: dict) -> str:
    return (
        f"event_type={entry['event_type']} "
        f"severity={entry['severity']} "
        f"user_id={entry.get('user_id')} "
        f"agent={entry.get('agent')} "
        f"preview={entry['content_preview']}"
    )
