import api from '@/utils/request'
import type { ExerciseRequest, ExerciseGradeRequest, ExerciseGradeResponse } from './types'

/**
 * 生成习题（SSE流式）
 * @param data - 习题生成请求
 */
export const generateExercise = (data: ExerciseRequest): Promise<Response> => {
  return fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/exercise/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(data)
  })
}

/**
 * 批改习题
 * @param data - 批改请求
 */
export const gradeExercise = (data: ExerciseGradeRequest): Promise<ExerciseGradeResponse> => {
  return api.post('/api/exercise/grade', data)
}

/**
 * 生成评估报告
 * @param evaluationResults - 评估结果
 */
export const generateEvaluationReport = (evaluationResults: Record<string, { score: number; total: number }>): Promise<void> => {
  return api.post('/api/exercise/report', { evaluation_results: evaluationResults })
}
