"""图谱域路由：知识图谱读取 / 图谱分析 / 图谱维护 / 可视化。"""

import logging

from fastapi import APIRouter

import internal_api as api
from app.api.errors import ErrorCode
from app.utils.prompt_guard import sanitize_model
from app.api.models import (
    GraphExtractRequest,
    GraphLayeredRequest,
    GraphMermaidRequest,
    GraphNodesRequest,
    GraphPrerequisiteRequest,
    GraphProgressRequest,
    GraphReloadRequest,
    GraphSuggestEdgesRequest,
    KnowledgeGraphNodeRequest,
    KnowledgeGraphRequest,
    MasteryUpdateRequest,
    NodeDeleteRequest,
    NodeUpdateRequest,
)

logger = logging.getLogger("internal_api")

router = APIRouter()


# ── Knowledge Graph ────────────────────────────────────────────

@router.post("/knowledge-graph/{course_id}")
async def get_knowledge_graph(course_id: str, body: KnowledgeGraphRequest):
    try:
        result = await api._get_graph_center().get_graph(
            course_id=course_id, masteries=body.masteries,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to get knowledge graph: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "获取知识图谱失败", status_code=500)


@router.post("/knowledge-graph/{course_id}/node/{node_id}")
async def get_node_card(course_id: str, node_id: str, body: KnowledgeGraphNodeRequest):
    try:
        result = await api._get_graph_center().get_node_card(
            course_id=course_id,
            node_id=node_id,
            masteries=body.masteries,
            total_exercises=body.total_exercises,
            last_practiced=body.last_practiced,
        )
        return api.api_success(result)
    except ValueError:
        return api.api_error(ErrorCode.NOT_FOUND, "节点不存在", status_code=404)
    except Exception as e:
        logger.error(f"Failed to get node card: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "获取节点卡片失败", status_code=500)


@router.post("/graph/extract")
async def graph_extract(body: GraphExtractRequest):
    # 模型参数清洗（P3-D）：user_message / assistant_reply 会进 LLM 抽取知识节点
    body = sanitize_model(body)
    try:
        result = await api._get_graph_center().extract_nodes(
            course_id=body.course_id,
            user_message=body.user_message,
            assistant_reply=body.assistant_reply,
            existing_node_ids=body.existing_node_ids,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to extract knowledge nodes: {e}", exc_info=True)
        return api.api_error(ErrorCode.GENERATION_FAILED, "知识节点提取失败", status_code=500)


@router.post("/graph/nodes")
async def graph_nodes(body: GraphNodesRequest):
    try:
        result = await api._get_graph_center().apply_updates(
            course_id=body.course_id,
            updates=[u.model_dump() for u in body.updates],
        )
        return api.api_success(result)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to apply graph updates: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "图谱更新失败", status_code=500)


@router.post("/graph/masteries")
async def update_masteries(body: MasteryUpdateRequest):
    """根据学习事件批量更新节点掌握度。Python 只计算，Java 自行持久化结果。"""
    result = await api._get_graph_center().update_masteries(
        course_id=body.course_id,
        masteries=body.masteries,
        events=[e.model_dump() for e in body.events],
    )
    return api.api_success(result)


@router.post("/graph/reload")
async def reload_graph(body: GraphReloadRequest):
    """热更新知识图谱骨架（管理员触发）。"""
    try:
        result = await api._get_graph_center().reload_skeleton()
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to reload graph skeleton: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "图谱热更新失败", status_code=500)


# ── Graph Phase A: 图谱分析 ────────────────────────────────────

@router.post("/graph/next-node")
async def recommend_next_node(body: GraphProgressRequest):
    """知识缺口分析：根据当前掌握度推荐下一个该学的节点。"""
    try:
        result = await api._get_graph_center().recommend_next_node(
            course_id=body.course_id, masteries=body.masteries,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to recommend next node: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "节点推荐失败", status_code=500)


@router.post("/graph/progress")
async def get_progress_summary(body: GraphProgressRequest):
    """学习进度概要：全局掌握率 + 各分类统计。"""
    try:
        result = await api._get_graph_center().progress_summary(
            course_id=body.course_id, masteries=body.masteries,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to get progress summary: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "进度概要获取失败", status_code=500)


@router.post("/graph/check-prerequisites")
async def check_prerequisites(body: GraphPrerequisiteRequest):
    """前置条件检查：用户是否可以学习指定节点。"""
    try:
        result = await api._get_graph_center().check_prerequisites(
            course_id=body.course_id,
            node_id=body.node_id,
            masteries=body.masteries,
            threshold=body.threshold,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to check prerequisites: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "前置条件检查失败", status_code=500)


# ── Graph Phase B: 图谱维护 ────────────────────────────────────

@router.post("/graph/nodes/{node_id}/delete")
async def delete_node(node_id: str, body: NodeDeleteRequest):
    """删除动态节点（骨架节点不可删）。"""
    try:
        result = await api._get_graph_center().delete_node(
            course_id=body.course_id, node_id=node_id,
        )
        return api.api_success(result)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to delete node: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "节点删除失败", status_code=500)


@router.post("/graph/nodes/{node_id}/update")
async def update_node(node_id: str, body: NodeUpdateRequest):
    """更新节点元数据。骨架节点仅可改 difficulty/category，动态节点全字段可改。"""
    try:
        result = await api._get_graph_center().update_node(
            course_id=body.course_id, node_id=node_id, updates=body.updates,
        )
        return api.api_success(result)
    except ValueError as e:
        return api.api_error(ErrorCode.INVALID_REQUEST, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Failed to update node: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "节点更新失败", status_code=500)


@router.post("/graph/suggest-edges")
async def suggest_edges(body: GraphSuggestEdgesRequest):
    """LLM 自动补边：分析未连通节点对，建议遗漏的图谱关系。"""
    try:
        result = await api._get_graph_center().suggest_edges(course_id=body.course_id)
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to suggest edges: {e}", exc_info=True)
        return api.api_error(ErrorCode.GENERATION_FAILED, "补边建议生成失败", status_code=500)


# ── Graph Phase C: 可视化 ──────────────────────────────────────

@router.post("/graph/export-mermaid")
async def export_mermaid(body: GraphMermaidRequest):
    """导出知识图谱为 Mermaid 流程图语法。"""
    try:
        result = await api._get_graph_center().export_mermaid(
            course_id=body.course_id, masteries=body.masteries,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to export mermaid: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "Mermaid 导出失败", status_code=500)


@router.post("/graph/layered")
async def get_layered_graph(body: GraphLayeredRequest):
    """返回带层级信息的图谱（前端分层布局）。"""
    try:
        result = await api._get_graph_center().layered_graph(
            course_id=body.course_id, masteries=body.masteries,
        )
        return api.api_success(result)
    except Exception as e:
        logger.error(f"Failed to get layered graph: {e}", exc_info=True)
        return api.api_error(ErrorCode.INTERNAL_ERROR, "分层图谱获取失败", status_code=500)
