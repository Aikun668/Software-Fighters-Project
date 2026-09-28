"""LearningSnapshot 只读端点（P1 §二，P2 Task 3）。

路由层只做两件事：
1. 从 GraphCenter 取图谱节点与推荐序列（图谱数据不进请求体，由本层补齐）；
2. 把请求体上下文原样转交给纯函数 `learning_snapshot.build_snapshot`。

零状态（P2 §五 边界规则 1）：不落库、不改计划、不改掌握度。图谱取数失败时
降级为「无图谱」而非 500 —— 快照本身允许 `current_node` 为 null。
"""

import logging

from fastapi import APIRouter
import internal_api as api
from app.api.errors import ErrorCode
from app.api.models import LearningSnapshotRequest
from app.services import learning_snapshot

logger = logging.getLogger("internal_api")
router = APIRouter()


@router.post("/snapshot")
async def get_learning_snapshot(body: LearningSnapshotRequest):
    """组装只读读模型 `LearningSnapshot`（P1 §二）。

    图谱 / 推荐序列属「可选富化」：取不到时如实反映在 `freshness.missing_sources`
    并在 `graph` 分支退化为 `next_ready` 缺失，不影响其余字段。
    """
    graph_nodes: list[dict] = []
    graph_edges: list[dict] = []
    recommended: list[dict] = []
    try:
        center = api._get_graph_center()
        graph = await center.get_graph(course_id=body.course_id, masteries=body.masteries)
        graph_nodes = (graph or {}).get("nodes") or []
        # `edges` 与 `nodes` 同属一次 get_graph 响应，切片零新增 IO；
        # `next_action` 行 4 的先修判定需要它（P1 §5.3）。
        graph_edges = (graph or {}).get("edges") or []
        progress = await center.recommend_next_node(
            course_id=body.course_id, masteries=body.masteries,
        )
        recommended = (progress or {}).get("recommended") or []
    except Exception as e:
        logger.error(f"Failed to load graph for snapshot: {e}", exc_info=True)

    try:
        result = learning_snapshot.build_snapshot(
            student_id=body.student_id,
            course_id=body.course_id,
            plan=body.plan,
            steps=body.steps,
            masteries=body.masteries,
            recent_evidence=[ev.model_dump() for ev in body.recent_evidence],
            student_profile=body.student_profile,
            recent_records=body.recent_records,
            session_analysis=body.session_analysis,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            recommended=recommended,
        )
    except Exception as e:
        logger.error(f"Failed to build learning snapshot: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "学习快照生成失败", status_code=500)
    return api.api_success(result)
