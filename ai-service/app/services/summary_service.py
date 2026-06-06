"""学习总结卡片服务 — 聚合会话模式路径、掌握度变化、下一步推荐"""

import logging
import threading
from typing import Optional

from sqlalchemy import select

from app.db.database import get_db
from app.models.conversation import Message
from app.models.node_mastery import NodeMastery

logger = logging.getLogger(__name__)


class SummaryService:
    """会话结束后聚合学习总结卡片"""

    async def get_session_summary(
        self,
        user_id: int,
        conversation_id: int,
        course_id: str = "ai_intro",
    ) -> dict:
        """聚合会话总结数据。

        返回:
          - topic: 话题（从消息提取关键词）
          - mode_path: 模式切换路径 ["tutor", "solve", "exercise"]
          - duration_minutes: 估算学习时长
          - mastery_changes: 掌握度分布 {mastered, in_progress, weak, overall_pct}
          - next_steps: 下一步推荐节点列表
          - generated_at: 生成时间 ISO 字符串
        """
        topic = ""
        mode_path: list[str] = []
        duration_minutes = 0

        # 从 Message 表提取 topic + mode_path + 时长
        try:
            async with get_db() as session:
                msg_result = await session.execute(
                    select(Message.mode, Message.content, Message.created_at)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.asc())
                    .limit(100)
                )
                rows = msg_result.all()
                modes_seen = []
                if rows:
                    first_ts = rows[0][2]
                    last_ts = rows[-1][2]
                    if first_ts and last_ts:
                        delta = (last_ts - first_ts).total_seconds()
                        duration_minutes = round(delta / 60, 1)

                    for mode, content, _ in rows:
                        if mode and mode not in modes_seen:
                            modes_seen.append(mode)

                mode_path = modes_seen or ["tutor"]

                # 简单 topic 提取：取首条用户消息的前 30 字
                first_user = await session.execute(
                    select(Message.content)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.role == "user",
                    )
                    .order_by(Message.created_at.asc())
                    .limit(1)
                )
                first_content = first_user.scalar()
                if first_content:
                    topic = first_content[:40] if isinstance(first_content, str) else ""

        except Exception as e:
            logger.warning(f"Session summary message query failed: {e}")

        # 掌握度分布 — 复用 NodeMastery 表
        mastery_changes = await self._query_mastery_distribution(user_id, course_id)

        # 下一步推荐 — 从图谱中找未掌握的节点
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

    async def _query_mastery_distribution(
        self, user_id: int, course_id: str
    ) -> dict:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(NodeMastery.mastery).where(
                        NodeMastery.user_id == user_id,
                        NodeMastery.course_id == course_id,
                    )
                )
                values = [r[0] or 0 for r in result.all()]

            if not values:
                return {"mastered": 0, "in_progress": 0, "weak": 0, "overall_pct": 0}

            mastered = sum(1 for v in values if v >= 0.7)
            in_progress = sum(1 for v in values if 0.3 <= v < 0.7)
            weak = sum(1 for v in values if v < 0.3)
            overall_pct = round(sum(values) / len(values) * 100, 1)
            return {
                "mastered": mastered,
                "in_progress": in_progress,
                "weak": weak,
                "overall_pct": overall_pct,
            }
        except Exception as e:
            logger.warning(f"Mastery distribution query failed: {e}")
            return {"mastered": 0, "in_progress": 0, "weak": 0, "overall_pct": 0}

    async def _query_next_steps(
        self, user_id: int, course_id: str, limit: int = 5
    ) -> list[dict]:
        """从未掌握或掌握度低的节点中推荐下一步"""
        try:
            from app.services.graph_service import get_graph_service

            gs = get_graph_service()
            skeleton = gs.load_skeleton()
            nodes = skeleton.get("nodes", [])
            edges = skeleton.get("edges", [])

            masteries = await gs._get_user_masteries(user_id, course_id)

            # 找到所有未完成节点
            unmastered = []
            for node in nodes:
                nid = node.get("id", "")
                m = masteries.get(nid, 0.0)
                if m < 0.7:
                    # 检查前置节点是否都已掌握
                    prereqs = [e["source"] for e in edges if e["target"] == nid]
                    prereqs_met = all(
                        masteries.get(p, 0.0) >= 0.7 for p in prereqs
                    )
                    priority = "high" if prereqs_met else "medium"
                    unmastered.append({
                        "node_id": nid,
                        "name": node.get("name", nid),
                        "mastery": round(m, 2),
                        "priority": priority,
                        "reason": "前置知识已掌握，可以推进" if prereqs_met
                        else f"前置: {', '.join(prereqs[:2])}",
                    })

            # 优先返回高优先级（前置满足）的
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
