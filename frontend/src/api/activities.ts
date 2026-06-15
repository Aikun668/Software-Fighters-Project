import api from '@/utils/request'
import type { LearningActivity, ScoreTrendItem } from './types'

/**
 * 记录学习活动
 * @param data - 活动数据
 */
export const recordLearningActivity = (data: LearningActivity): Promise<LearningActivity> => {
  return api.post('/api/learning-activities', data)
}

/**
 * 获取最近活动列表
 * @param userId - 用户ID
 * @param limit - 数量限制（可选）
 */
export const getRecentActivities = (userId: number, limit?: number): Promise<LearningActivity[]> => {
  const params = limit ? { userId, limit } : { userId }
  return api.get('/api/learning-activities', params)
}

/**
 * 获取活动统计
 * @param userId - 用户ID
 */
export const getActivityStats = (userId: number): Promise<Record<string, number>> => {
  return api.get('/api/learning-activities/stats', { userId })
}

/**
 * 获取得分趋势
 * @param userId - 用户ID
 * @param days - 天数（可选，默认30）
 */
export const getScoreTrend = (userId: number, days?: number): Promise<ScoreTrendItem[]> => {
  const params = days ? { userId, days } : { userId }
  return api.get('/api/learning-activities/score-trend', params)
}

/**
 * 获取习题计数
 * @param userId - 用户ID
 */
export const getExerciseCount = (userId: number): Promise<{ count: number }> => {
  return api.get('/api/learning-activities/count-exercises', { userId })
}
