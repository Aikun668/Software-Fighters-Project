import api from '@/utils/request'

/**
 * 发送消息
 * @param data - 消息数据
 */
export const sendMessage = (data: {
  userId: string
  content: string
  type?: string
}) => {
  return api.post('/chat/message', data)
}

/**
 * 获取聊天历史
 * @param userId - 用户ID
 * @param params - 查询参数
 */
export const getChatHistory = (userId: string, params?: {
  page?: number
  size?: number
}) => {
  return api.get(`/chat/history/${userId}`, params)
}

/**
 * 获取AI回复
 * @param data - 请求数据
 */
export const getAIResponse = (data: {
  message: string
  context?: string[]
  model?: string
}) => {
  return api.post('/chat/ai', data)
}

/**
 * 获取对话列表
 * @param userId - 用户ID
 */
export const getConversations = (userId: string) => {
  return api.get(`/chat/conversations/${userId}`)
}

/**
 * 创建新对话
 * @param userId - 用户ID
 */
export const createConversation = (userId: string) => {
  return api.post(`/chat/conversations/${userId}`)
}

/**
 * 删除对话
 * @param conversationId - 对话ID
 */
export const deleteConversation = (conversationId: string) => {
  return api.delete(`/chat/conversations/${conversationId}`)
}
