import api from '@/utils/request'
import type { Conversation, Message, ChatRequest, ChatSSEEvent } from './types'

/**
 * 统一对话 - 发起对话（SSE流式）
 * @param data - 对话请求数据
 */
export const chatWithAI = (data: ChatRequest): Promise<Response> => {
  return fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(data)
  })
}

/**
 * 解析SSE事件流
 * @param response - fetch响应
 * @param onMessage - 消息回调
 * @param onComplete - 完成回调
 */
export const parseSSEStream = (
  response: Response,
  onMessage: (event: ChatSSEEvent) => void,
  onComplete: () => void
): (() => void) => {
  const reader = response.body?.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const read = async () => {
    if (!reader) return

    try {
      const { done, value } = await reader.read()
      
      if (done) {
        onComplete()
        return
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.substring(6)
          if (data === '[DONE]') {
            onComplete()
            return
          }
          try {
            const event: ChatSSEEvent = JSON.parse(data)
            onMessage(event)
          } catch (e) {
            console.error('Failed to parse SSE event:', e)
          }
        }
      }

      read()
    } catch (e) {
      console.error('SSE stream error:', e)
      onComplete()
    }
  }

  read()

  return () => {
    reader?.cancel()
  }
}

/**
 * 获取会话列表
 */
export const getConversations = (): Promise<Conversation[]> => {
  return api.get('/conversations/mine')
}

/**
 * 创建会话
 */
export const createConversation = (): Promise<Conversation> => {
  return api.post('/conversations', {})
}

/**
 * 获取会话详情
 * @param id - 会话ID
 * @param userId - 用户ID（可选）
 */
export const getConversationDetail = (id: number, userId?: number): Promise<Conversation> => {
  const params = userId ? { userId } : {}
  return api.get(`/conversations/${id}`, params)
}

/**
 * 更新会话
 * @param id - 会话ID
 * @param data - 更新数据
 */
export const updateConversation = (id: number, data: { title?: string; status?: string }): Promise<Conversation> => {
  return api.put(`/conversations/${id}`, data)
}

/**
 * 获取会话消息列表
 * @param id - 会话ID
 * @param params - 查询参数
 */
export const getConversationMessages = (id: number, params?: { mode?: string; limit?: number }): Promise<Message[]> => {
  return api.get(`/conversations/${id}/messages`, params)
}

/**
 * 获取原始消息（分页）
 * @param id - 会话ID
 * @param params - 查询参数
 */
export const getRawMessages = (id: number, params?: { offset?: number; limit?: number }): Promise<Message[]> => {
  return api.get(`/conversations/${id}/messages/raw`, params)
}

/**
 * 手动保存消息
 * @param id - 会话ID
 * @param data - 消息数据
 */
export const saveMessage = (id: number, data: { user_message: string; assistant_message: string }): Promise<void> => {
  return api.post(`/conversations/${id}/messages`, data)
}

/**
 * 结束会话
 * @param id - 会话ID
 */
export const endConversation = (id: number): Promise<void> => {
  return api.post(`/conversations/${id}/end`)
}

/**
 * 删除会话
 * @param id - 会话ID
 */
export const deleteConversation = (id: number): Promise<void> => {
  return api.delete(`/conversations/${id}`)
}
