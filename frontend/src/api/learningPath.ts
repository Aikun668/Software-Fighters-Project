import api from '@/utils/request'

/**
 * 获取学习路径列表
 */
export const getLearningPaths = () => {
  return api.get('/learning-paths')
}

/**
 * 获取学习路径详情
 * @param pathId - 学习路径ID
 */
export const getLearningPathDetail = (pathId: string) => {
  return api.get(`/learning-paths/${pathId}`)
}

/**
 * 获取用户学习路径进度
 * @param userId - 用户ID
 */
export const getUserPathProgress = (userId: string) => {
  return api.get(`/users/${userId}/path-progress`)
}

/**
 * 开始学习路径
 * @param pathId - 学习路径ID
 */
export const startLearningPath = (pathId: string) => {
  return api.post(`/learning-paths/${pathId}/start`)
}

/**
 * 获取学习路径中的课程
 * @param pathId - 学习路径ID
 */
export const getPathCourses = (pathId: string) => {
  return api.get(`/learning-paths/${pathId}/courses`)
}

/**
 * 获取学习路径阶段
 * @param pathId - 学习路径ID
 */
export const getPathStages = (pathId: string) => {
  return api.get(`/learning-paths/${pathId}/stages`)
}
