import api from '@/utils/request'
import type { LearningRecord, RecordStats } from './types'

/**
 * 获取我的学习记录
 */
export const getMyRecords = (): Promise<LearningRecord[]> => {
  return api.get('/api/record/list')
}

/**
 * 按类型筛选记录
 * @param type - 记录类型
 */
export const getRecordsByType = (type: 'course_doc' | 'mind_map' | 'exercise' | 'reading' | 'code_practice'): Promise<LearningRecord[]> => {
  return api.get(`/api/record/list/${type}`)
}

/**
 * 获取某资源的记录
 * @param resourceId - 资源ID
 */
export const getResourceRecord = (resourceId: number): Promise<LearningRecord> => {
  return api.get(`/api/record/resource/${resourceId}`)
}

/**
 * 获取学习统计
 */
export const getRecordStats = (): Promise<RecordStats> => {
  return api.get('/api/record/stats')
}
