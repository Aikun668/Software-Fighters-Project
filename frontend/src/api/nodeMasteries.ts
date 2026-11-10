import api from '@/utils/request'
import type { NodeMastery } from './types'

/**
 * 获取用户课程所有掌握度
 * @param userId - 用户ID
 * @param courseId - 课程ID
 */
export const getUserCourseMasteries = (userId: number, courseId: string): Promise<NodeMastery[]> => {
  return api.get('/node-masteries', { userId, courseId })
}

/**
 * 获取单个节点掌握度
 * @param nodeId - 节点ID
 * @param userId - 用户ID
 */
export const getNodeMastery = (nodeId: string, userId: number): Promise<NodeMastery> => {
  return api.get(`/node-masteries/${nodeId}`, { userId })
}

/**
 * 更新掌握度
 * @param nodeId - 节点ID
 * @param data - 更新数据
 */
export const updateNodeMastery = (nodeId: string, data: {
  user_id: number
  course_id: string
  mastery: number
  review_count: number
}): Promise<NodeMastery> => {
  return api.put(`/node-masteries/${nodeId}`, data)
}

/**
 * 获取掌握度分布统计
 * @param userId - 用户ID
 * @param courseId - 课程ID
 */
export const getMasteryDistributionStats = (userId: number, courseId: string): Promise<Record<string, number>> => {
  return api.get('/node-masteries/distribution', { userId, courseId })
}
