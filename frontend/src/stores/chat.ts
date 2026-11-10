import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 聊天消息接口定义
 * 支持SSE流式响应
 */
export interface ChatMessage {
  id: string                 // 消息唯一标识
  role: 'user' | 'assistant' // 角色：用户或助手
  content: string            // 消息内容
  timestamp: number          // 发送时间戳
  streaming?: boolean        // 是否正在流式传输中
}

/**
 * 对话状态管理Store
 * 负责管理智能答疑的对话状态，支持SSE流式响应
 * 
 * @description
 * 核心功能：
 * - 维护消息列表（用户消息 + AI回复）
 * - 支持后端SSE推送的流式数据处理
 * - 管理流式响应状态（开始/进行中/结束）
 * - 提供消息增删操作
 */
export const useChatStore = defineStore('chat', () => {
  // 状态定义
  const messages = ref<ChatMessage[]>([])           // 消息列表
  const isStreaming = ref(false)                    // 是否正在接收流式响应
  const currentStreamId = ref<string | null>(null)   // 当前流式消息ID

  /**
   * 添加新消息
   * @param message - 消息对象（自动添加时间戳）
   */
  function addMessage(message: Omit<ChatMessage, 'timestamp'>) {
    messages.value.push({
      ...message,
      timestamp: Date.now()
    })
  }

  /**
   * 更新流式消息内容
   * 用于实时显示SSE推送的数据
   * @param content - 新的消息内容
   */
  function updateStreamContent(content: string) {
    if (currentStreamId.value) {
      const message = messages.value.find(m => m.id === currentStreamId.value)
      if (message) {
        message.content = content
      }
    }
  }

  /**
   * 结束流式响应
   * 标记流式消息完成，并重置状态
   */
  function endStream() {
    isStreaming.value = false
    if (currentStreamId.value) {
      const message = messages.value.find(m => m.id === currentStreamId.value)
      if (message) {
        message.streaming = false
      }
    }
    currentStreamId.value = null
  }

  /**
   * 开始流式响应
   * @param messageId - 流式消息的ID
   */
  function startStream(messageId: string) {
    isStreaming.value = true
    currentStreamId.value = messageId
  }

  /**
   * 清空所有消息
   */
  function clearMessages() {
    messages.value = []
  }

  return {
    messages,
    isStreaming,
    addMessage,
    updateStreamContent,
    startStream,
    endStream,
    clearMessages
  }
})