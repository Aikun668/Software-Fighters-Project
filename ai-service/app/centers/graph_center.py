"""图谱域唯一业务入口。

收口前 14 个图谱端点的业务逻辑散在 `internal_api.py` 的路由体内（含 4 处内联
实现）；本 Center 把它们收成方法，API 只做「校验 → 一次 Center 调用 → 序列化」。

约定：
- 方法签名用**关键字参数**，与路由体的调用一一对应，便于逐字比对。
- 本 Center 负责**信封组装**（`{"recommended": ...}` / `{"mermaid": ...}` /
  `{"suggestions": ...}` 等），API 不再拼响应体。
- 业务异常**原样上抛**（`ValueError` → API 映射 400/404），本 Center 不做
  HTTP 语义映射、不 import fastapi。
"""

import logging

from app.services.graph_service import get_graph_service

logger = logging.getLogger(__name__)


class GraphCenter:
    def __init__(self, graph_service=None, plan_service=None, extraction=None):
        self._graph_service = graph_service
        self._plan_service = plan_service
        self._extraction = extraction

    def _graph(self):
        return self._graph_service or get_graph_service()

    # ── 读路径 ────────────────────────────────────────────────────

    async def get_graph(self, *, course_id: str, masteries: dict) -> dict:
        return await self._graph().get_graph(course_id=course_id, masteries=masteries)

    async def get_node_card(
        self,
        *,
        course_id: str,
        node_id: str,
        masteries: dict,
        total_exercises: int = 0,
        last_practiced: str | None = None,
    ) -> dict:
        return await self._graph().get_node_card(
            node_id=node_id,
            course_id=course_id,
            masteries=masteries,
            total_exercises=total_exercises,
            last_practiced=last_practiced,
        )

    async def recommend_next_node(self, *, course_id: str, masteries: dict) -> dict:
        candidates = self._graph().recommend_next_node(masteries, course_id)
        return {"recommended": candidates}

    async def progress_summary(self, *, course_id: str, masteries: dict) -> dict:
        return self._graph().get_progress_summary(masteries, course_id)

    async def check_prerequisites(
        self,
        *,
        course_id: str,
        node_id: str,
        masteries: dict,
        threshold: float,
    ) -> dict:
        return self._graph().check_prerequisites(node_id, masteries, threshold, course_id)

    async def export_mermaid(self, *, course_id: str, masteries: dict) -> dict:
        mermaid = self._graph().export_mermaid(course_id, masteries)
        return {"mermaid": mermaid}

    async def layered_graph(self, *, course_id: str, masteries: dict) -> dict:
        return self._graph().get_layered_graph(masteries, course_id)

    async def suggest_edges(self, *, course_id: str) -> dict:
        suggestions = await self._graph().suggest_edges(course_id)
        return {"suggestions": suggestions}
