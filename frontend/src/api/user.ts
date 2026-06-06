import type { UserProfile } from '@/types';
import api from '@/utils/request'

/**
 * 获取验证码
 * @param email - 邮箱地址
 */
export const getCaptcha = (email: string) => {
  return api.post('/auth/captcha', { email })
}

/**
 * 验证验证码
 * @param data - 验证信息
 */
export const verifyCaptcha = (data: { email: string; captcha: string }) => {
  return api.post('/auth/captcha/verify', data)
}

/**
 * 用户登录
 * @param data - 登录信息
 */
export const login = (data: { email: string; password: string; captcha?: string }) => {
  return api.post('/auth/login', data)
}

/**
 * 用户注册
 * @param data - 注册信息
 */
export const register = (data: {
  username: string
  email: string
  password: string
}) => {
  return api.post('/auth/register', data)
}

/**
 * 获取用户信息
 * @param userId - 用户ID
 */
export const getUserInfo = (userId: string) => {
  return api.get(`/users/${userId}`)
}

/**
 * 更新用户信息
 * @param userId - 用户ID
 * @param data - 更新的用户信息
 */
export const updateUserInfo = (userId: string, data: Partial<UserProfile>) => {
  return api.put(`/users/${userId}`, data)
}

/**
 * 获取用户学习统计
 * @param userId - 用户ID
 */
export const getUserStats = (userId: string) => {
  return api.get(`/users/${userId}/stats`)
}

/**
 * 获取用户学习路径
 * @param userId - 用户ID
 */
export const getUserLearningPath = (userId: string) => {
  return api.get(`/users/${userId}/learning-path`)
}

/**
 * 更新用户学习目标
 * @param userId - 用户ID
 * @param goals - 学习目标列表
 */
export const updateLearningGoals = (userId: string, goals: string[]) => {
  return api.put(`/users/${userId}/goals`, { goals })
}

/**
 * 更新用户兴趣标签
 * @param userId - 用户ID
 * @param interests - 兴趣标签列表
 */
export const updateInterests = (userId: string, interests: string[]) => {
  return api.put(`/users/${userId}/interests`, { interests })
}

/**
 * 退出登录
 */
export const logout = () => {
  return api.post('/auth/logout')
}
