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

    # ── 写路径 ────────────────────────────────────────────────────

    async def apply_updates(self, *, course_id: str, updates: list[dict]) -> dict:
        """按序 dispatch add_node / add_edge，然后重取整图作为响应。"""
        graph = self._graph()
        for update in updates:
            action = update.get("action")
            if action == "add_node":
                graph.add_node(course_id, update["data"])
            elif action == "add_edge":
                graph.add_edge(course_id, update["data"])
        return await graph.get_graph(course_id=course_id)

    async def update_masteries(
        self,
        *,
        course_id: str,
        masteries: dict,
        events: list[dict],
    ) -> dict:
        """按学习事件累积掌握度。Python 只计算，Java 自行持久化结果。"""
        plan_service = self._plan_service or _plan_service_cls()
        result = dict(masteries)
        for event in events:
            node_id = event["node_id"]
            current = result.get(node_id, 0.0)
            result[node_id] = plan_service.update_mastery(
                current, event["event_type"], event.get("score")
            )
        return {"masteries": result}

    async def reload_skeleton(self) -> dict:
        """强制重载骨架，计数取自**原始骨架**（不含 parallel 补边与运行时变异）。"""
        graph = self._graph().load_skeleton(force_reload=True)
        return {
            "status": "reloaded",
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
        }

    async def delete_node(self, *, course_id: str, node_id: str) -> dict:
        deleted = self._graph().delete_node(course_id, node_id)
        return {"deleted": deleted, "node_id": node_id}

    async def update_node(self, *, course_id: str, node_id: str, updates: dict) -> dict:
        return {"node": self._graph().update_node(course_id, node_id, updates)}

    # ── 抽取入口 ──────────────────────────────────────────────────

    async def extract_nodes(
        self,
        *,
        course_id: str,
        user_message: str,
        assistant_reply: str,
        existing_node_ids: list[str] | None = None,
    ) -> dict:
        """知识节点抽取。`all` 组在响应里改名为 `candidates`（对外契约）。

        与 `ChatCenter.stream_chat()` 的推荐抽取是两条独立入口，共用底层
        `extract_knowledge_nodes`。
        """
        extraction = self._extraction or _extraction_func()
        groups = await extraction(
            course_id=course_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            existing_node_ids=existing_node_ids,
        )
        return {
            "primary": groups.get("primary", []),
            "related": groups.get("related", []),
            "broad": groups.get("broad", []),
            "candidates": groups.get("all", []),
        }


def _plan_service_cls():
    from app.services.plan_service import PlanService

    return PlanService


def _extraction_func():
    from app.services.knowledge_extraction import extract_knowledge_nodes

    return extract_knowledge_nodes
