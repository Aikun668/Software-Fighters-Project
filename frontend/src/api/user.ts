import api from '@/utils/request'
import type { UserRegisterRequest, UserLoginRequest, UserProfile } from './types'

/**
 * 用户注册
 * @param data - 注册信息
 */
export const register = (data: UserRegisterRequest): Promise<UserProfile> => {
  return api.post('/user/register', data)
}

/**
 * 用户登录
 * @param data - 登录信息
 */
export const login = (data: UserLoginRequest): Promise<{ data: string; }> => {
  return api.post('/user/login', data)
}

/**
 * 获取用户信息
 * @param userId - 用户ID
 */
export const getUserInfo = (userId: number): Promise<UserProfile> => {
  return api.get(`/user/${userId}`)
}

/**
 * 更新用户信息
 * @param userId - 用户ID
 * @param data - 更新的用户信息
 */
export const updateUserInfo = (userId: number, data: Partial<UserProfile>): Promise<UserProfile> => {
  return api.put(`/user/${userId}`, data)
}

/**
 * 退出登录
 */
export const logout = (): Promise<void> => {
  return api.post('/user/logout')
}

/**
 * 获取验证码图片
 */
export const getCaptcha = (): Promise<{ captchaKey: string; captchaImage: string }> => {
  return api.get('/user/captcha')
}
