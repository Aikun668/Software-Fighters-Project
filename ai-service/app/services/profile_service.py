"""画像持久化服务 — 通过 Java API 进行画像 CRUD"""

import logging
import threading
from typing import Optional

from app.services.java_api_client import get_java_client

logger = logging.getLogger(__name__)


class ProfileService:

    def __init__(self):
        self._client = get_java_client()

    async def get_profile(self, user_id: int) -> dict | None:
        try:
            return await self._client.get_profile(user_id)
        except Exception as e:
            logger.warning(f"Failed to get profile for user {user_id}: {e}")
            return None

    async def incremental_update(self, user_id: int, evaluation_report: dict) -> None:
        """评估后增量更新画像：条目模型叠加 weak_points"""
        try:
            profile = await self._client.get_profile(user_id)
            if not profile:
                logger.warning(f"No profile found for user_id={user_id}, skipping update")
                return

            old_kb = profile.get("knowledge_base", 0) or 0
            overall = evaluation_report.get("overall_score", 0)
            new_kb = min(100, max(0, int(old_kb * 0.7 + overall * 0.3)))

            new_weak = evaluation_report.get("recommended_weak_points", [])
            weak_points = profile.get("weak_points", []) or []
            entries = dict(profile.get("entries", {}) or {})
            dim_entries = list(entries.get("weak_points", []))

            if new_weak:
                from app.agents.profile_agent import (
                    DEDUP_SIMILARITY,
                    MAX_ENTRIES_PER_DIM,
                    MIN_CONFIDENCE_FOR_ACTIVE,
                    _bigram_jaccard,
                )
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()

                for item in new_weak:
                    text = item if isinstance(item, str) else item.get("text", "")
                    if not text:
                        continue

                    matched = False
                    for existing in dim_entries:
                        if _bigram_jaccard(text, existing.get("text", "")) > DEDUP_SIMILARITY:
                            existing["confidence"] = min(existing.get("confidence", 1) + 1, 10)
                            existing["updated_at"] = now
                            if existing["confidence"] >= MIN_CONFIDENCE_FOR_ACTIVE:
                                existing["status"] = "active"
                            matched = True
                            break

                    if not matched:
                        dim_entries.append({
                            "text": text,
                            "confidence": 1,
                            "status": "tentative",
                            "created_at": now,
                            "updated_at": now,
                        })

                if len(dim_entries) > MAX_ENTRIES_PER_DIM:
                    status_order = {"active": 0, "tentative": 1, "stale": 2}
                    dim_entries.sort(
                        key=lambda e: (
                            status_order.get(e.get("status", "active"), 0),
                            -e.get("confidence", 1),
                        )
                    )
                    dim_entries = dim_entries[:MAX_ENTRIES_PER_DIM]

                entries["weak_points"] = dim_entries
                weak_points = sorted(
                    [e["text"] for e in dim_entries],
                    key=lambda t: next(
                        (e["confidence"] for e in dim_entries if e["text"] == t), 1
                    ),
                    reverse=True,
                )

            await self._client.update_profile(user_id, {
                "knowledge_base": new_kb,
                "weak_points": weak_points,
                "entries": entries,
            })

            logger.info(
                f"Profile updated for user_id={user_id}: kb={new_kb}, "
                f"weak_points={weak_points}"
            )
        except Exception as e:
            logger.warning(f"Failed to update profile for user {user_id}: {e}")

    async def save_profile(self, user_id: int, profile_dict: dict) -> None:
        try:
            await self._client.upsert_profile(user_id, profile_dict)
        except Exception as e:
            logger.warning(f"Failed to save profile for user {user_id}: {e}")


_service: Optional[ProfileService] = None
_service_lock = threading.Lock()


def get_profile_service() -> ProfileService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = ProfileService()
    return _service
