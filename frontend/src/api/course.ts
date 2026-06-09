import api from '@/utils/request'

/**
 * 获取课程列表
 * @param params - 查询参数
 */
export const getCourseList = (params?: {
  page?: number
  size?: number
  category?: string
  keyword?: string
}) => {
  return api.get('/courses', params)
}

/**
 * 获取课程详情
 * @param courseId - 课程ID
 */
export const getCourseDetail = (courseId: string) => {
  return api.get(`/courses/${courseId}`)
}

/**
 * 获取课程章节列表
 * @param courseId - 课程ID
 */
export const getCourseChapters = (courseId: string) => {
  return api.get(`/courses/${courseId}/chapters`)
}

/**
 * 获取章节内容
 * @param chapterId - 章节ID
 */
export const getChapterContent = (chapterId: string) => {
  return api.get(`/chapters/${chapterId}`)
}

/**
 * 获取课程分类
 */
export const getCourseCategories = () => {
  return api.get('/courses/categories')
}

/**
 * 用户开始学习课程
 * @param courseId - 课程ID
 */
export const startCourse = (courseId: string) => {
  return api.post(`/courses/${courseId}/start`)
}

/**
 * 用户完成章节
 * @param chapterId - 章节ID
 */
export const completeChapter = (chapterId: string) => {
  return api.post(`/chapters/${chapterId}/complete`)
}

/**
 * 获取用户学习进度
 * @param courseId - 课程ID
 */
export const getCourseProgress = (courseId: string) => {
  return api.get(`/courses/${courseId}/progress`)
}

/**
 * 获取推荐课程
 * @param userId - 用户ID
 */
export const getRecommendedCourses = (userId: string) => {
  return api.get(`/users/${userId}/recommendations`)
}

/**
 * 获取热门课程
 */
export const getHotCourses = () => {
  return api.get('/courses/hot')
}
