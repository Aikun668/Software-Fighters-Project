import api from '@/utils/request'
import type { KnowledgeGraph, KnowledgeNode } from './types'

/**
 * 获取课程知识图谱
 * @param courseId - 课程ID
 * @param userId - 用户ID（可选）
 */
export const getKnowledgeGraph = (courseId: string, userId?: number): Promise<KnowledgeGraph> => {
  const params = userId ? { userId } : {}
  return api.get(`/api/knowledge-graph/${courseId}`, params)
}

/**
 * 获取节点详情卡片
 * @param courseId - 课程ID
 * @param nodeId - 节点ID
 * @param params - 查询参数
 */
export const getNodeDetail = (
  courseId: string,
  nodeId: string,
  params?: { userId?: number; totalExercises?: number; lastPracticed?: string }
): Promise<KnowledgeNode> => {
  return api.get(`/api/knowledge-graph/${courseId}/nodes/${nodeId}`, params)
}

/**
 * 获取节点掌握度分布
 * @param courseId - 课程ID
 * @param userId - 用户ID
 */
export const getMasteryDistribution = (courseId: string, userId: number): Promise<Record<string, number>> => {
  return api.get(`/api/knowledge-graph/masteries/${courseId}`, { userId })
}
