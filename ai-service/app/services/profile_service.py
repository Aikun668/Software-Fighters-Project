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
                }
        except Exception as e:
            logger.warning(f"Failed to get profile for user {user_id}: {e}")
            return None

    async def incremental_update(self, user_id: int, evaluation_report: dict) -> None:
        """评估后增量更新画像：使用 tag_weights 动态权重叠加 weak_points"""
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

                # ── weak_points: 用 tag_weights 动态叠加 ──
                tag_weights = dict(profile.tag_weights or {})
                wp_weights = dict(tag_weights.get("weak_points", {}))
                new_weak = evaluation_report.get("recommended_weak_points", [])

                from app.agents.profile_agent import TAG_CUTOFF, TAG_EMA_ALPHA

                # 未被本次评估命中的 → 衰减
                new_set = set(new_weak)
                for tag in list(wp_weights.keys()):
                    if tag not in new_set:
                        decayed = round(wp_weights[tag] * (1 - TAG_EMA_ALPHA), 2)
                        if decayed >= TAG_CUTOFF:
                            wp_weights[tag] = decayed
                        else:
                            del wp_weights[tag]

                # 本次命中的 → EMA 增强
                for tag in new_weak:
                    old_w = wp_weights.get(tag, 0.0)
                    wp_weights[tag] = round(
                        old_w * (1 - TAG_EMA_ALPHA) + TAG_EMA_ALPHA, 2
                    )

                tag_weights["weak_points"] = wp_weights
                profile.tag_weights = tag_weights

                # 同步旧版 list 字段
                profile.weak_points = sorted(
                    wp_weights.keys(), key=lambda k: wp_weights[k], reverse=True
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
