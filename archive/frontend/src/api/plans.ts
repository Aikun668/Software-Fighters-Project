import api from '@/utils/request'
import type { LearningPlan, PlanStep } from './types'

/**
 * 创建学习计划（含步骤）
 * @param data - 计划数据
 */
export const createPlan = (data: {
  user_id: number
  course_id: string
  title: string
  steps: PlanStep[]
}): Promise<LearningPlan> => {
  return api.post('/plans', data)
}

/**
 * 获取计划详情（含步骤）
 * @param id - 计划ID
 * @param userId - 用户ID（可选）
 */
export const getPlanDetail = (id: number, userId?: number): Promise<LearningPlan> => {
  const params = userId ? { userId } : {}
  return api.get(`/plans/${id}`, params)
}

/**
 * 更新计划
 * @param id - 计划ID
 * @param data - 更新数据
 */
export const updatePlan = (id: number, data: { title?: string; status?: 'in_progress' | 'completed' | 'paused' }): Promise<LearningPlan> => {
  return api.put(`/plans/${id}`, data)
}

/**
 * 获取计划步骤列表
 * @param planId - 计划ID
 */
export const getPlanSteps = (planId: number): Promise<PlanStep[]> => {
  return api.get(`/plans/${planId}/steps`)
}

/**
 * 添加步骤
 * @param planId - 计划ID
 * @param data - 步骤数据
 */
export const addPlanStep = (planId: number, data: {
  node_id: string
  topic: string
  order: number
  node_type: 'learn' | 'practice'
  depth?: number
}): Promise<PlanStep> => {
  return api.post(`/plans/${planId}/steps`, data)
}

/**
 * 步骤排序位移
 * @param planId - 计划ID
 * @param afterOrder - 插入位置
 */
export const shiftPlanStep = (planId: number, afterOrder: number): Promise<void> => {
  return api.post(`/plans/${planId}/steps/shift`, { after_order: afterOrder })
}

/**
 * 锁定后继节点
 * @param planId - 计划ID
 * @param nodeId - 节点ID
 */
export const lockSuccessors = (planId: number, nodeId: string): Promise<void> => {
  return api.post(`/plans/${planId}/steps/lock-successors`, { node_id: nodeId })
}

/**
 * 节点状态变更（原子操作）
 * @param data - 状态变更数据
 */
export const changeNodeStatus = (data: {
  user_id: number
  node_id: string
  new_status: 'completed' | 'in_progress' | 'pending'
  plan_id: number
}): Promise<void> => {
  return api.post('/plans/node-status-change', data)
}

/**
 * 更新单个步骤
 * @param stepId - 步骤ID
 * @param data - 更新数据
 */
export const updatePlanStep = (stepId: number, data: {
  status?: 'pending' | 'in_progress' | 'completed' | 'locked'
  order?: number
}): Promise<PlanStep> => {
  return api.put(`/plan-steps/${stepId}`, data)
}

export interface PlanProgressRequest {
  step_id: number
  step_order: number
  status: 'completed' | 'in_progress' | 'pending'
  activity_type: 'study' | 'review' | 'exercise'
  score: number
  duration_minutes: number
}

export interface PlanProgressResponse {
  status?: string
  message?: string
  [key: string]: unknown
}

/** 将学习入口承接的计划动作提交给 Java 计划进度接口。 */
export const updatePlanProgress = (
  planId: number,
  data: PlanProgressRequest,
): Promise<PlanProgressResponse> => {
  return api.post(`/plans/${planId}/progress`, data)
}
