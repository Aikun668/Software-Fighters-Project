import type { Component } from 'vue'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** 该轮用户消息附带的图片 URL（仅用户消息使用，用于气泡内回显缩略图） */
  images?: string[]
  /** 后端返回的真实错误信息；有值时不得用任何本地内容顶替 */
  error?: string
  streaming?: boolean
}

export type ChatMode = 'auto' | 'plan' | 'resource' | 'exercise'
export type ChatStyle = 'standard' | 'socratic'

export interface ChatAttachment {
  fileId: number
  name: string
  url: string
  /**
   * 是否为图片附件。
   * 附件可以是任意文件；但只有图片能作为多模态内容送给 AI（后端 images 字段），
   * 也才用缩略图展示，其余文件用通用文件图标。
   */
  isImage: boolean
}

export interface ChatSuggestion {
  label: string
  icon: Component
  path: string
}

