"""DashboardService — 学生仪表盘聚合服务

为侧边栏「我的学习」和「学习分析」提供聚合数据：
  - profile: 6 维度学习画像
  - memory: 学习轨迹（活动时间线 + 概念掌握分布）
  - evaluation: 能力评估（模块得分 + 趋势 + 雷达图数据）

所有数据来自 Java API，不直接访问 DB。
"""

import json
import logging
import os

from app.services.java_api_client import get_java_client

logger = logging.getLogger(__name__)

SKELETON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "knowledge_graph_skeleton.json"
)


class DashboardService:

    def __init__(self):
        self._client = get_java_client()

    async def get_dashboard(self, user_id: int, course_id: str = "ai_intro") -> dict:
        return {
            "profile": await self._get_profile_section(user_id),
            "memory": await self._get_memory_section(user_id, course_id),
            "evaluation": await self._get_evaluation_section(user_id, course_id),
        }

    # ── Section 1: 学习画像 ──────────────────────────────────────

    async def _get_profile_section(self, user_id: int) -> dict:
        try:
            profile = await self._client.get_profile(user_id)
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

        entries = profile.get("entries", {}) or {}
        weak_points = self._extract_active_entries(entries.get("weak_points", []))
        interests = self._extract_active_entries(entries.get("interest_direction", []))

        filled = 0
        if profile.get("knowledge_base") and profile["knowledge_base"] > 0:
            filled += 1
        if profile.get("cognitive_style"):
            filled += 1
        if profile.get("learning_goal"):
            filled += 1
        if weak_points:
            filled += 1
        if profile.get("learning_pace"):
            filled += 1
        if interests:
            filled += 1

        return {
            "knowledge_base": profile.get("knowledge_base") or 0,
            "cognitive_style": profile.get("cognitive_style"),
            "learning_goal": profile.get("learning_goal"),
            "learning_pace": profile.get("learning_pace"),
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

    async def _get_memory_section(self, user_id: int, course_id: str) -> dict:
        node_map = self._load_node_map()

        recent = await self._query_recent_activities(user_id, node_map)

        try:
            masteries_dict = await self._client.get_node_masteries(user_id, course_id)
        except Exception as e:
            logger.error(f"Dashboard mastery query failed: {e}")
            masteries_dict = {}

        mastered = []
        in_progress = []
        weak = []
        for node_id, mastery_val in masteries_dict.items():
            name = node_map.get(node_id, {}).get("name", node_id) if node_map else node_id
            entry = {"node_id": node_id, "name": name, "mastery": round(mastery_val or 0, 2)}
            if (mastery_val or 0) >= 0.7:
                mastered.append(entry)
            elif (mastery_val or 0) >= 0.3:
                in_progress.append(entry)
            else:
                weak.append(entry)

        mastered.sort(key=lambda x: -x["mastery"])
        in_progress.sort(key=lambda x: -x["mastery"])
        weak.sort(key=lambda x: x["mastery"])

        try:
            stats = await self._client.get_activity_stats(user_id)
        except Exception as e:
            logger.error(f"Dashboard activity stats failed: {e}")
            stats = {}

        return {
            "recent_activities": recent,
            "mastered_concepts": mastered,
            "in_progress_concepts": in_progress,
            "weak_concepts": weak,
            "total_study_sessions": stats.get("total_sessions", 0),
            "total_study_minutes": stats.get("total_minutes", 0),
            "first_study_date": stats.get("first_date"),
            "last_study_date": stats.get("last_date"),
        }

    async def _query_recent_activities(
        self, user_id: int, node_map: dict[str, dict] | None = None, limit: int = 20,
    ) -> list[dict]:
        try:
            activities = await self._client.get_recent_activities(user_id, limit)
        except Exception:
            return []

        if node_map is None:
            node_map = self._load_node_map()

        output = []
        for a in activities:
            topic = a.get("topic", "")
            if not topic and a.get("knowledge_node_id") and node_map:
                topic = node_map.get(a["knowledge_node_id"], {}).get("name", "")

            output.append({
                "date": a.get("created_at"),
                "type": a.get("activity_type", "study"),
                "topic": topic,
                "score": a.get("score"),
                "duration_minutes": a.get("duration_minutes"),
            })

        return output

    # ── Section 3: 学习评估 ──────────────────────────────────────

    async def _get_evaluation_section(self, user_id: int, course_id: str) -> dict:
        topic_mastery = await self._query_topic_mastery(user_id)
        distribution = self._calc_distribution(topic_mastery)
        score_trend = await self._query_score_trend(user_id)
        profile_dims = await self._query_profile_dimensions(user_id)

        weak_modules = [t["topic"] for t in topic_mastery if t["mastery"] < 0.4]

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
            return await self._client.get_topic_mastery_aggregation(user_id)
        except Exception as e:
            logger.error(f"Dashboard topic mastery query failed: {e}")
            return []

    @staticmethod
    def _calc_distribution(topic_mastery: list[dict]) -> dict:
        mastered = sum(1 for t in topic_mastery if t.get("mastery", 0) >= 0.7)
        in_progress = sum(1 for t in topic_mastery if 0.3 <= t.get("mastery", 0) < 0.7)
        weak = sum(1 for t in topic_mastery if t.get("mastery", 0) < 0.3)
        return {"mastered": mastered, "in_progress": in_progress, "weak": weak}

    async def _query_score_trend(self, user_id: int, days: int = 30) -> list[dict]:
        try:
            return await self._client.get_score_trend(user_id, days)
        except Exception as e:
            logger.error(f"Dashboard score trend query failed: {e}")
            return []

    async def _query_profile_dimensions(self, user_id: int) -> dict:
        try:
            profile = await self._client.get_profile(user_id)
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

        entries = profile.get("entries", {}) or {}
        weak_count = len(self._extract_active_entries(entries.get("weak_points", [])))
        interest_count = len(self._extract_active_entries(entries.get("interest_direction", [])))

        return {
            "knowledge_base": profile.get("knowledge_base") or 0,
            "cognitive_style_score": 80 if profile.get("cognitive_style") else 30,
            "learning_goal_clarity": 80 if profile.get("learning_goal") else 20,
            "weak_points_coverage": max(100 - weak_count * 12, 10),
            "learning_pace_score": 80 if profile.get("learning_pace") else 30,
            "interest_breadth": min(interest_count * 15, 100),
        }

    @staticmethod
    def _load_node_map() -> dict[str, dict]:
        try:
            with open(SKELETON_PATH, "r", encoding="utf-8") as f:
                skeleton = json.load(f)
            return {n["id"]: n for n in skeleton.get("nodes", [])}
        except Exception:
            return {}
