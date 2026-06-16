import api from '@/utils/request'

/**
 * 获取学习路径
 * @param userId - 用户ID
 */
export const getLearningPath = (userId: number): Promise<any> => {
  return api.get(`/api/path/${userId}`)
}
