"""学习总结卡片服务 — 聚合会话模式路径、掌握度变化、下一步推荐"""

import logging
import threading
from typing import Optional

from app.services.java_api_client import get_java_client

logger = logging.getLogger(__name__)


class SummaryService:
    """会话结束后聚合学习总结卡片"""

    def __init__(self):
        self._client = get_java_client()

    async def get_session_summary(
        self, user_id: int, conversation_id: int, course_id: str = "ai_intro",
    ) -> dict:
        topic = ""
        mode_path: list[str] = []
        duration_minutes = 0

        try:
            messages = await self._client.load_messages_raw(conversation_id, offset=0, limit=100)
            modes_seen = []
            if messages:
                first_ts = messages[0].get("created_at")
                last_ts = messages[-1].get("created_at")
                if first_ts and last_ts:
                    try:
                        from datetime import datetime
                        t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                        t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                        delta = (t2 - t1).total_seconds()
                        duration_minutes = round(delta / 60, 1)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse message timestamps: {e}")

                for m in messages:
                    mode = m.get("mode")
                    if mode and mode not in modes_seen:
                        modes_seen.append(mode)

            mode_path = modes_seen or ["tutor"]

            # 取首条用户消息的前 40 字作为 topic
            first_user_msg = next(
                (m.get("content", "") for m in messages if m.get("role") == "user"),
                "",
            )
            if first_user_msg:
                topic = first_user_msg[:40] if isinstance(first_user_msg, str) else ""

        except Exception as e:
            logger.warning(f"Session summary message query failed: {e}")

        mastery_changes = await self._query_mastery_distribution(user_id, course_id)
        next_steps = await self._query_next_steps(user_id, course_id)

        from datetime import datetime, timezone
        return {
            "topic": topic,
            "mode_path": mode_path,
            "duration_minutes": duration_minutes,
            "mastery_changes": mastery_changes,
            "next_steps": next_steps,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _query_mastery_distribution(self, user_id: int, course_id: str) -> dict:
        try:
            return await self._client.get_mastery_distribution(user_id, course_id)
        except Exception as e:
            logger.warning(f"Mastery distribution query failed: {e}")
            return {"mastered": 0, "in_progress": 0, "weak": 0, "overall_pct": 0}

    async def _query_next_steps(self, user_id: int, course_id: str, limit: int = 5) -> list[dict]:
        try:
            from app.services.graph_service import get_graph_service

            gs = get_graph_service()
            skeleton = gs.load_skeleton()
            nodes = skeleton.get("nodes", [])
            edges = skeleton.get("edges", [])

            masteries = await gs._get_user_masteries(user_id, course_id)

            unmastered = []
            for node in nodes:
                nid = node.get("id", "")
                m = masteries.get(nid, 0.0)
                if m < 0.7:
                    prereqs = [e["source"] for e in edges if e["target"] == nid]
                    prereqs_met = all(masteries.get(p, 0.0) >= 0.7 for p in prereqs)
                    priority = "high" if prereqs_met else "medium"
                    unmastered.append({
                        "node_id": nid,
                        "name": node.get("name", nid),
                        "mastery": round(m, 2),
                        "priority": priority,
                        "reason": "前置知识已掌握，可以推进" if prereqs_met
                        else f"前置: {', '.join(prereqs[:2])}",
                    })

            unmastered.sort(key=lambda x: (0 if x["priority"] == "high" else 1, x["mastery"]))
            return unmastered[:limit]

        except Exception as e:
            logger.warning(f"Next steps query failed: {e}")
            return []


_service: Optional[SummaryService] = None
_service_lock = threading.Lock()


def get_summary_service() -> SummaryService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = SummaryService()
    return _service
