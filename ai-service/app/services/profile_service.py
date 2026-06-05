import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from app.db.database import get_db
from app.models.profile import StudentProfile

logger = logging.getLogger(__name__)


class ProfileService:
    async def get_profile(self, user_id: int) -> dict | None:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
                if profile is None:
                    return None
                return {
                    "knowledge_base": profile.knowledge_base,
                    "cognitive_style": profile.cognitive_style,
                    "learning_goal": profile.learning_goal,
                    "weak_points": profile.weak_points or [],
                    "learning_pace": profile.learning_pace,
                    "interest_direction": profile.interest_direction or [],
                    "tag_weights": profile.tag_weights or {},
                    "stability_counter": profile.stability_counter or {},
                    "entries": profile.entries or {},
                    "audit_counter": profile.audit_counter or 0,
                }
        except Exception as e:
            logger.warning(f"Failed to get profile for user {user_id}: {e}")
            return None

    async def incremental_update(self, user_id: int, evaluation_report: dict) -> None:
        """评估后增量更新画像：条目模型叠加 weak_points"""
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile)
                    .where(StudentProfile.user_id == user_id)
                    .with_for_update()
                )
                profile = result.scalar_one_or_none()
                if not profile:
                    logger.warning(f"No profile found for user_id={user_id}, skipping update")
                    return

                # ── knowledge_base: EMA 不变 ──
                old_kb = profile.knowledge_base or 0
                overall = evaluation_report.get("overall_score", 0)
                new_kb = min(100, max(0, int(old_kb * 0.7 + overall * 0.3)))
                profile.knowledge_base = new_kb

                # ── weak_points: 条目模型叠加 ──
                new_weak = evaluation_report.get("recommended_weak_points", [])
                if new_weak:
                    from datetime import timezone
                    from datetime import datetime as dt

                    from app.agents.profile_agent import (
                        DEDUP_SIMILARITY,
                        MAX_ENTRIES_PER_DIM,
                        MIN_CONFIDENCE_FOR_ACTIVE,
                        _bigram_jaccard,
                    )

                    db_entries = dict(profile.entries or {})
                    dim_entries = list(db_entries.get("weak_points", []))
                    now = dt.now(timezone.utc).isoformat()

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

                    db_entries["weak_points"] = dim_entries
                    profile.entries = db_entries

                    # 向后兼容同步
                    profile.weak_points = sorted(
                        [e["text"] for e in dim_entries],
                        key=lambda t: next(
                            (e["confidence"] for e in dim_entries if e["text"] == t), 1
                        ),
                        reverse=True,
                    )

                await session.commit()
            logger.info(
                f"Profile updated for user_id={user_id}: kb={new_kb}, "
                f"weak_points={profile.weak_points}"
            )
        except Exception as e:
            logger.warning(f"Failed to update profile for user {user_id}: {e}")

    async def save_profile(self, user_id: int, profile_dict: dict) -> None:
        try:
            async with get_db() as session:
                stmt = insert(StudentProfile).values(
                    user_id=user_id,
                    knowledge_base=profile_dict.get("knowledge_base", 0),
                    cognitive_style=profile_dict.get("cognitive_style"),
                    learning_goal=profile_dict.get("learning_goal"),
                    weak_points=profile_dict.get("weak_points", []),
                    learning_pace=profile_dict.get("learning_pace"),
                    interest_direction=profile_dict.get("interest_direction", []),
                    tag_weights=profile_dict.get("tag_weights", {}),
                    stability_counter=profile_dict.get("stability_counter", {}),
                    entries=profile_dict.get("entries", {}),
                )
                stmt = stmt.on_duplicate_key_update(
                    knowledge_base=stmt.inserted.knowledge_base,
                    cognitive_style=stmt.inserted.cognitive_style,
                    learning_goal=stmt.inserted.learning_goal,
                    weak_points=stmt.inserted.weak_points,
                    learning_pace=stmt.inserted.learning_pace,
                    interest_direction=stmt.inserted.interest_direction,
                    tag_weights=stmt.inserted.tag_weights,
                    stability_counter=stmt.inserted.stability_counter,
                    entries=stmt.inserted.entries,
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to save profile for user {user_id}: {e}")


_service: Optional[ProfileService] = None


def get_profile_service() -> ProfileService:
    global _service
    if _service is None:
        _service = ProfileService()
    return _service
