"""Java API 客户端 — 集中式异步 HTTP 调用 Java 后端

替换所有 SQLAlchemy 直接 DB 访问。
AI 逻辑（LangGraph、LLM、RAG、SSE）不在此层。
"""

import logging
import os
import threading
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8080/api"
DEFAULT_TIMEOUT = 10.0


class JavaApiError(Exception):
    """Java API 调用异常基类"""


class JavaApiTimeoutError(JavaApiError):
    """Java API 超时"""


class JavaApiHttpError(JavaApiError):
    """Java API HTTP 4xx/5xx 错误"""

    def __init__(self, status_code: int, url: str, message: str = ""):
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code}: {url}" + (f" — {message}" if message else ""))


class JavaApiConnectionError(JavaApiError):
    """Java API 连接/网络错误"""


class JavaApiClient:
    """Java 后端 REST API 客户端（async, httpx-based）"""

    def __init__(self, base_url: str = "", timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url or os.getenv("JAVA_API_BASE_URL", DEFAULT_BASE_URL)
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── 内部工具 ───────────────────────────────────────────────

    async def _get(self, path: str, **kwargs) -> dict | list | None:
        try:
            client = await self._ensure_client()
            resp = await client.get(path, **kwargs)
            return self._extract_data(resp)
        except httpx.TimeoutException:
            logger.warning(f"Java API timeout: GET {path}")
            raise JavaApiTimeoutError(f"GET {path}") from None
        except JavaApiError:
            raise
        except Exception as e:
            logger.warning(f"Java API error: GET {path} — {e}")
            raise JavaApiConnectionError(f"GET {path}: {e}") from e

    async def _post(self, path: str, body: dict = None, **kwargs) -> dict | None:
        try:
            client = await self._ensure_client()
            resp = await client.post(path, json=body or {}, **kwargs)
            return self._extract_data(resp)
        except httpx.TimeoutException:
            logger.warning(f"Java API timeout: POST {path}")
            raise JavaApiTimeoutError(f"POST {path}") from None
        except JavaApiError:
            raise
        except Exception as e:
            logger.warning(f"Java API error: POST {path} — {e}")
            raise JavaApiConnectionError(f"POST {path}: {e}") from e

    async def _put(self, path: str, body: dict = None, **kwargs) -> dict | None:
        try:
            client = await self._ensure_client()
            resp = await client.put(path, json=body or {}, **kwargs)
            return self._extract_data(resp)
        except httpx.TimeoutException:
            logger.warning(f"Java API timeout: PUT {path}")
            raise JavaApiTimeoutError(f"PUT {path}") from None
        except JavaApiError:
            raise
        except Exception as e:
            logger.warning(f"Java API error: PUT {path} — {e}")
            raise JavaApiConnectionError(f"PUT {path}: {e}") from e

    @staticmethod
    def _extract_data(resp: httpx.Response) -> dict | list | None:
        if resp.status_code >= 400:
            raise JavaApiHttpError(
                resp.status_code, str(resp.url),
                resp.text[:200] if resp.text else "",
            )
        body = resp.json()
        if isinstance(body, dict) and body.get("code") == 0:
            return body.get("data")
        return body

    # ═══════════════════════════════════════════════════════════
    # Conversation / Message
    # ═══════════════════════════════════════════════════════════

    async def create_conversation(self, user_id: int) -> dict | None:
        return await self._post("/conversations", {"user_id": user_id})

    async def get_conversation(self, conversation_id: int, user_id: int) -> dict | None:
        return await self._get(f"/conversations/{conversation_id}", params={"user_id": user_id})

    async def update_conversation(self, conversation_id: int, data: dict) -> dict | None:
        return await self._put(f"/conversations/{conversation_id}", data)

    async def delete_conversation(self, conversation_id: int, user_id: int) -> dict | None:
        raise NotImplementedError("delete_conversation 尚未由 Java 后端实现")

    async def load_messages(
        self, conversation_id: int, mode_filter: str | None = None, limit: int = 50
    ) -> list[dict]:
        params = {"limit": limit}
        if mode_filter:
            params["mode"] = mode_filter
        result = await self._get(f"/conversations/{conversation_id}/messages", params=params)
        return result if isinstance(result, list) else []

    async def load_messages_raw(
        self, conversation_id: int, offset: int = 0, limit: int = 200
    ) -> list[dict]:
        result = await self._get(
            f"/conversations/{conversation_id}/messages/raw",
            params={"offset": offset, "limit": limit},
        )
        return result if isinstance(result, list) else []

    async def save_messages(
        self,
        conversation_id: int,
        user_msg: str,
        assistant_msg: str,
        user_mode: str = "tutor",
        assistant_mode: str = "tutor",
    ) -> None:
        await self._post(
            f"/conversations/{conversation_id}/messages",
            {
                "user_message": user_msg,
                "assistant_message": assistant_msg,
                "user_mode": user_mode,
                "assistant_mode": assistant_mode,
            },
        )

    # ═══════════════════════════════════════════════════════════
    # StudentProfile
    # ═══════════════════════════════════════════════════════════

    async def get_profile(self, user_id: int) -> dict | None:
        result = await self._get(f"/profiles/{user_id}")
        return result if isinstance(result, dict) else None

    async def upsert_profile(self, user_id: int, profile_dict: dict) -> dict | None:
        return await self._put(f"/profiles/{user_id}", profile_dict)

    async def update_profile(self, user_id: int, partial: dict) -> dict | None:
        return await self._post(f"/profiles/{user_id}", partial)

    # ═══════════════════════════════════════════════════════════
    # LearningPlan + PlanStep
    # ═══════════════════════════════════════════════════════════

    async def create_plan(
        self, user_id: int, course_id: str, title: str, steps: list[dict]
    ) -> dict | None:
        return await self._post(
            "/plans",
            {
                "user_id": user_id,
                "course_id": course_id,
                "title": title,
                "steps": steps,
            },
        )

    async def get_plan(self, plan_id: int, user_id: int) -> dict | None:
        result = await self._get(f"/plans/{plan_id}", params={"user_id": user_id})
        return result if isinstance(result, dict) else None

    async def get_plan_steps(self, plan_id: int) -> list[dict]:
        result = await self._get(f"/plans/{plan_id}/steps")
        return result if isinstance(result, list) else []

    async def update_plan(self, plan_id: int, data: dict) -> dict | None:
        return await self._put(f"/plans/{plan_id}", data)

    async def update_plan_step(self, step_id: int, data: dict) -> dict | None:
        return await self._put(f"/plan-steps/{step_id}", data)

    async def insert_plan_step(self, plan_id: int, step_data: dict) -> dict | None:
        return await self._post(f"/plans/{plan_id}/steps", step_data)

    async def shift_step_orders(self, plan_id: int, after_order: int) -> dict | None:
        return await self._post(
            f"/plans/{plan_id}/steps/shift", {"after_order": after_order}
        )

    async def lock_successor_steps(self, plan_id: int, node_id: str) -> list[int] | None:
        result = await self._post(
            f"/plans/{plan_id}/steps/lock-successors", {"node_id": node_id}
        )
        if isinstance(result, dict):
            return result.get("locked_ids", [])
        return None

    async def on_node_status_change(
        self, user_id: int, node_id: str, old_status: str,
        new_status: str, plan_id: int = None,
    ) -> dict | None:
        body = {
            "user_id": user_id,
            "node_id": node_id,
            "old_status": old_status,
            "new_status": new_status,
        }
        if plan_id:
            body["plan_id"] = plan_id
        return await self._post("/plans/node-status-change", body)

    # ═══════════════════════════════════════════════════════════
    # NodeMastery
    # ═══════════════════════════════════════════════════════════

    async def get_node_masteries(self, user_id: int, course_id: str) -> dict[str, float]:
        result = await self._get(
            "/node-masteries", params={"user_id": user_id, "course_id": course_id}
        )
        if isinstance(result, list):
            return {item["node_id"]: item.get("mastery", 0.0) for item in result}
        if isinstance(result, dict):
            return {k: float(v) for k, v in result.items()}
        return {}

    async def get_node_mastery_detail(self, user_id: int, node_id: str) -> dict | None:
        result = await self._get(
            f"/node-masteries/{node_id}", params={"user_id": user_id}
        )
        return result if isinstance(result, dict) else None

    async def upsert_node_mastery(
        self, user_id: int, node_id: str, course_id: str,
        mastery: float, review_count: int,
    ) -> dict | None:
        return await self._put(
            f"/node-masteries/{node_id}",
            {
                "user_id": user_id,
                "course_id": course_id,
                "mastery": mastery,
                "review_count": review_count,
            },
        )

    async def get_mastery_distribution(self, user_id: int, course_id: str) -> dict:
        result = await self._get(
            "/node-masteries/distribution",
            params={"user_id": user_id, "course_id": course_id},
        )
        if isinstance(result, dict):
            return result
        return {"mastered": 0, "in_progress": 0, "weak": 0, "overall_pct": 0}

    # ═══════════════════════════════════════════════════════════
    # LearningActivity
    # ═══════════════════════════════════════════════════════════

    async def create_activity(
        self, user_id: int, plan_id: int, step_id: int,
        activity_type: str, duration_minutes: int = 0, score: float = None,
    ) -> dict | None:
        body = {
            "user_id": user_id,
            "plan_id": plan_id,
            "step_id": step_id,
            "activity_type": activity_type,
            "duration_minutes": duration_minutes,
        }
        if score is not None:
            body["score"] = score
        return await self._post("/learning-activities", body)

    async def get_recent_activities(self, user_id: int, limit: int = 20) -> list[dict]:
        result = await self._get(
            "/learning-activities", params={"user_id": user_id, "limit": limit}
        )
        return result if isinstance(result, list) else []

    async def get_activity_stats(self, user_id: int) -> dict:
        result = await self._get(
            "/learning-activities/stats", params={"user_id": user_id}
        )
        if isinstance(result, dict):
            return result
        return {
            "total_sessions": 0, "total_minutes": 0,
            "first_date": None, "last_date": None,
        }

    async def get_score_trend(self, user_id: int, days: int = 30) -> list[dict]:
        result = await self._get(
            "/learning-activities/score-trend",
            params={"user_id": user_id, "days": days},
        )
        return result if isinstance(result, list) else []

    async def count_exercises(self, user_id: int) -> int:
        result = await self._get(
            "/learning-activities/count-exercises", params={"user_id": user_id}
        )
        if isinstance(result, dict):
            return result.get("count", 0)
        if isinstance(result, int):
            return result
        return 0

    # ═══════════════════════════════════════════════════════════
    # Resource
    # ═══════════════════════════════════════════════════════════

    async def create_resource(
        self, user_id: int, resource_type: str, topic: str, title: str, content_json: dict,
    ) -> int:
        result = await self._post(
            "/resources",
            {
                "user_id": user_id,
                "type": resource_type,
                "topic": topic,
                "title": title,
                "content_json": content_json,
            },
        )
        if isinstance(result, dict):
            return result.get("id", 0)
        return 0

    async def create_resources_batch(self, resources: list[dict]) -> list[int]:
        """批量创建资源，返回 resource_id 列表"""
        result = await self._post("/resources/batch", {"resources": resources})
        if isinstance(result, list):
            return [r.get("id", 0) if isinstance(r, dict) else 0 for r in result]
        if isinstance(result, dict):
            return result.get("ids", [])
        return []

    # ═══════════════════════════════════════════════════════════
    # LearningRecord
    # ═══════════════════════════════════════════════════════════

    async def create_learning_record(
        self, user_id: int, resource_id: int, progress: float = 0.0,
    ) -> int:
        result = await self._post(
            "/learning-records",
            {
                "user_id": user_id,
                "resource_id": resource_id,
                "progress": progress,
            },
        )
        if isinstance(result, dict):
            return result.get("id", 0)
        return 0

    # ═══════════════════════════════════════════════════════════
    # 聚合查询
    # ═══════════════════════════════════════════════════════════

    async def get_topic_mastery_aggregation(self, user_id: int) -> list[dict]:
        """按 topic 聚合掌握度（JOIN PlanStep + LearningPlan）"""
        result = await self._get(
            "/aggregations/topic-mastery", params={"user_id": user_id}
        )
        return result if isinstance(result, list) else []


# ── 单例工厂 ──────────────────────────────────────────────────

_client: Optional[JavaApiClient] = None
_client_lock = threading.Lock()


def get_java_client() -> JavaApiClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = JavaApiClient()
    return _client
