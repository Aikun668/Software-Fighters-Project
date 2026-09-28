import api from '@/utils/request'
import type { ProfileChatRequest, ProfileStatus, UserProfile } from './types'

/**
 * 画像对话（SSE流式）
 * @param data - 对话请求数据
 */
export const profileChat = (data: ProfileChatRequest): Promise<Response> => {
  return fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/profile/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(data)
  })
}

/**
 * 获取画像完整度
 */
export const getProfileStatus = (): Promise<ProfileStatus> => {
  return api.get('/profile/status')
}

/**
 * 获取用户画像
 * @param userId - 用户ID
 */
export const getUserProfile = (userId: number): Promise<UserProfile> => {
  return api.get(`/profile/${userId}`)
}
