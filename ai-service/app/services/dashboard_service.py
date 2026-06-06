"""DashboardService — 学生仪表盘聚合服务

为侧边栏「我的学习」和「学习分析」提供聚合数据：
  - profile: 6 维度学习画像
  - memory: 学习轨迹（活动时间线 + 概念掌握分布）
  - evaluation: 能力评估（模块得分 + 趋势 + 雷达图数据）

所有数据来自现有 DB 表，不引入新的基础设施。
"""

import json
import logging
import os
from datetime import date, datetime, timezone, timedelta

from sqlalchemy import select, func

from app.db.database import get_db
from app.models.profile import StudentProfile
from app.models.node_mastery import NodeMastery
from app.models.learning_activity import LearningActivity
from app.models.learning_plan import LearningPlan, PlanStep

logger = logging.getLogger(__name__)

SKELETON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "knowledge_graph_skeleton.json"
)


class DashboardService:

    async def get_dashboard(
        self, user_id: int, course_id: str = "ai_intro",
    ) -> dict:
        return {
            "profile": await self._get_profile_section(user_id),
            "memory": await self._get_memory_section(user_id, course_id),
            "evaluation": await self._get_evaluation_section(user_id, course_id),
        }

    # ── Section 1: 学习画像 ──────────────────────────────────────

    async def _get_profile_section(self, user_id: int) -> dict:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Dashboard profile query failed: {e}")
            profile = None

        if profile is None:
            return {
                "knowledge_base": 0,
                "cognitive_style": None,
                "learning_goal": None,
                "learning_pace": None,
                "weak_points": [],
                "interest_direction": [],
                "filled_dimensions": 0,
            }

        entries = profile.entries or {}
        weak_points = self._extract_active_entries(entries.get("weak_points", []))
        interests = self._extract_active_entries(entries.get("interest_direction", []))

        # 统计已填充维度
        filled = 0
        if profile.knowledge_base and profile.knowledge_base > 0:
            filled += 1
        if profile.cognitive_style:
            filled += 1
        if profile.learning_goal:
            filled += 1
        if weak_points:
            filled += 1
        if profile.learning_pace:
            filled += 1
        if interests:
            filled += 1

        return {
            "knowledge_base": profile.knowledge_base or 0,
            "cognitive_style": profile.cognitive_style,
            "learning_goal": profile.learning_goal,
            "learning_pace": profile.learning_pace,
            "weak_points": weak_points,
            "interest_direction": interests,
            "filled_dimensions": filled,
        }

    @staticmethod
    def _extract_active_entries(entries: list) -> list[dict]:
        if not isinstance(entries, list):
            return []
        result = []
        for e in entries:
            if isinstance(e, dict) and e.get("status") != "archived":
                result.append({
                    "text": e.get("text", ""),
                    "confidence": e.get("confidence", 0.5),
                })
        return result

    # ── Section 2: 学习轨迹 ──────────────────────────────────────

    async def _get_memory_section(
        self, user_id: int, course_id: str,
    ) -> dict:
        node_map = self._load_node_map()

        # 最近活动（传入 node_map 避免重复读文件）
        recent = await self._query_recent_activities(user_id, node_map)

        # 概念掌握分布
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(NodeMastery).where(
                        NodeMastery.user_id == user_id,
                        NodeMastery.course_id == course_id,
                    )
                )
                masteries = result.scalars().all()
        except Exception as e:
            logger.error(f"Dashboard mastery query failed: {e}")
            masteries = []

        mastered = []
        in_progress = []
        weak = []
        for m in masteries:
            name = node_map.get(m.node_id, {}).get("name", m.node_id) if node_map else m.node_id
            entry = {
                "node_id": m.node_id,
                "name": name,
                "mastery": round(m.mastery or 0, 2),
                "last_review_at": m.last_review_at.isoformat() if m.last_review_at else None,
            }
            if (m.mastery or 0) >= 0.7:
                mastered.append(entry)
            elif (m.mastery or 0) >= 0.3:
                in_progress.append(entry)
            else:
                weak.append(entry)

        mastered.sort(key=lambda x: -x["mastery"])
        in_progress.sort(key=lambda x: -x["mastery"])
        weak.sort(key=lambda x: x["mastery"])

        # 统计
        try:
            async with get_db() as session:
                count_result = await session.execute(
                    select(
                        func.count(LearningActivity.id),
                        func.coalesce(func.sum(LearningActivity.duration_minutes), 0),
                        func.min(LearningActivity.created_at),
                        func.max(LearningActivity.created_at),
                    ).where(LearningActivity.user_id == user_id)
                )
                row = count_result.one()
                total_sessions = row[0]
                total_minutes = row[1] or 0
                first_date = row[2].isoformat() if row[2] else None
                last_date = row[3].isoformat() if row[3] else None
        except Exception as e:
            logger.error(f"Dashboard activity stats failed: {e}")
            total_sessions = 0
            total_minutes = 0
            first_date = None
            last_date = None

        return {
            "recent_activities": recent,
            "mastered_concepts": mastered,
            "in_progress_concepts": in_progress,
            "weak_concepts": weak,
            "total_study_sessions": total_sessions,
            "total_study_minutes": total_minutes,
            "first_study_date": first_date,
            "last_study_date": last_date,
        }

    async def _query_recent_activities(
        self, user_id: int, node_map: dict[str, dict] | None = None, limit: int = 20,
    ) -> list[dict]:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(LearningActivity)
                    .where(LearningActivity.user_id == user_id)
                    .order_by(LearningActivity.created_at.desc())
                    .limit(limit)
                )
                activities = result.scalars().all()
        except Exception:
            return []

        if node_map is None:
            node_map = self._load_node_map()

        # 批量预加载 PlanStep，避免 N+1
        step_ids = [a.step_id for a in activities if a.step_id]
        step_map: dict[int, dict] = {}
        if step_ids:
            try:
                async with get_db() as session:
                    step_result = await session.execute(
                        select(PlanStep.id, PlanStep.topic, PlanStep.knowledge_node_id)
                        .where(PlanStep.id.in_(step_ids))
                    )
                    for row in step_result:
                        step_map[row[0]] = {"topic": row[1] or "", "knowledge_node_id": row[2] or ""}
            except Exception:
                pass

        output = []
        for a in activities:
            topic = ""
            if a.step_id and a.step_id in step_map:
                step_info = step_map[a.step_id]
                topic = step_info["topic"]
                if not topic and step_info.get("knowledge_node_id") and node_map:
                    topic = node_map.get(step_info["knowledge_node_id"], {}).get("name", "")

            output.append({
                "date": a.created_at.isoformat() if a.created_at else None,
                "type": a.activity_type or "study",
                "topic": topic,
                "score": a.score,
                "duration_minutes": a.duration_minutes,
            })

        return output

    # ── Section 3: 学习评估 ──────────────────────────────────────

    async def _get_evaluation_section(
        self, user_id: int, course_id: str,
    ) -> dict:
        # 3a. 按 topic 的掌握度
        topic_mastery = await self._query_topic_mastery(user_id)

        # 3b. 掌握度分布
        distribution = self._calc_distribution(topic_mastery)

        # 3c. 近 30 天分数趋势
        score_trend = await self._query_score_trend(user_id)

        # 3d. 画像维度雷达图数据
        profile_dims = await self._query_profile_dimensions(user_id)

        # 3e. 薄弱模块
        weak_modules = [
            t["topic"] for t in topic_mastery
            if t["mastery"] < 0.4
        ]

        # 综合分
        if topic_mastery:
            overall = round(sum(t["mastery"] for t in topic_mastery) / len(topic_mastery) * 100)
        else:
            overall = 0

        return {
            "topic_mastery": topic_mastery,
            "mastery_distribution": distribution,
            "score_trend": score_trend,
            "profile_dimensions": profile_dims,
            "overall_score": overall,
            "weak_modules": weak_modules,
        }

    async def _query_topic_mastery(self, user_id: int) -> list[dict]:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(
                        PlanStep.topic,
                        func.avg(PlanStep.mastery_current).label("avg_mastery"),
                        func.avg(PlanStep.topic_difficulty).label("avg_difficulty"),
                    )
                    .join(LearningPlan, PlanStep.plan_id == LearningPlan.id)
                    .where(
                        LearningPlan.user_id == user_id,
                        PlanStep.mastery_current.isnot(None),
                    )
                    .group_by(PlanStep.topic)
                    .order_by(func.avg(PlanStep.mastery_current).desc())
                )
                rows = result.all()
        except Exception as e:
            logger.error(f"Dashboard topic mastery query failed: {e}")
            return []

        return [
            {
                "topic": row[0] or "",
                "mastery": round(row[1] or 0, 2),
                "difficulty": round(row[2] or 3),
            }
            for row in rows
        ]

    @staticmethod
    def _calc_distribution(topic_mastery: list[dict]) -> dict:
        mastered = sum(1 for t in topic_mastery if t["mastery"] >= 0.7)
        in_progress = sum(1 for t in topic_mastery if 0.3 <= t["mastery"] < 0.7)
        weak = sum(1 for t in topic_mastery if t["mastery"] < 0.3)
        return {"mastered": mastered, "in_progress": in_progress, "weak": weak}

    async def _query_score_trend(
        self, user_id: int, days: int = 30,
    ) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(
                        func.date(LearningActivity.created_at).label("day"),
                        func.round(func.avg(LearningActivity.score), 2).label("avg_score"),
                        func.count(LearningActivity.id).label("session_count"),
                    )
                    .where(
                        LearningActivity.user_id == user_id,
                        LearningActivity.score.isnot(None),
                        LearningActivity.created_at >= cutoff,
                    )
                    .group_by(func.date(LearningActivity.created_at))
                    .order_by("day")
                )
                rows = result.all()
        except Exception as e:
            logger.error(f"Dashboard score trend query failed: {e}")
            return []

        return [
            {"date": str(row[0]), "avg_score": float(row[1] or 0), "session_count": int(row[2])}
            for row in rows
        ]

    async def _query_profile_dimensions(self, user_id: int) -> dict:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
        except Exception:
            profile = None

        if profile is None:
            return {
                "knowledge_base": 0,
                "cognitive_style_score": 0,
                "learning_goal_clarity": 0,
                "weak_points_coverage": 0,
                "learning_pace_score": 0,
                "interest_breadth": 0,
            }

        entries = profile.entries or {}
        weak_count = len(self._extract_active_entries(entries.get("weak_points", [])))
        interest_count = len(self._extract_active_entries(entries.get("interest_direction", [])))

        return {
            "knowledge_base": profile.knowledge_base or 0,
            "cognitive_style_score": 80 if profile.cognitive_style else 30,
            "learning_goal_clarity": 80 if profile.learning_goal else 20,
            "weak_points_coverage": max(100 - weak_count * 12, 10),
            "learning_pace_score": 80 if profile.learning_pace else 30,
            "interest_breadth": min(interest_count * 15, 100),
        }

    # ── 工具方法 ─────────────────────────────────────────────────

    @staticmethod
    def _load_node_map() -> dict[str, dict]:
        try:
            with open(SKELETON_PATH, "r", encoding="utf-8") as f:
                skeleton = json.load(f)
            return {n["id"]: n for n in skeleton.get("nodes", [])}
        except Exception:
            return {}
