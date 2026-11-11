import api from '@/utils/request'
import { dispatchUiBlock, type DispatchResult } from '@/components/chat/ui-blocks/registry'

export const USER_RETRY = '刚才没写完，你的问题还在，再发一次即可'

/** 流式失败。conversationId 有值时，这次失败仍然属于那条会话。 */
export class ChatStreamError extends Error {
  conversationId: number | null
  code: string | null

  constructor(message: string, conversationId: number | null = null, code: string | null = null) {
    super(message)
    this.name = 'ChatStreamError'
    this.conversationId = conversationId
    this.code = code
  }
}

export interface SseStreamHooks {
  onRetract?: () => void
  onConversationId?: (conversationId: number) => void
  onRecommendation?: (recommendation: { label: string; prompt: string }) => void
}

const messageForStatus = (status: number) => {
  if (status === 401) return '请先登录，再继续提问'
  if (status === 404) return '这条对话找不到了，可以新开一条再问'
  return USER_RETRY
}

/**
 * 发送消息（SSE流式）
 * @param data - 消息数据
 *   - messages: 前端仍会带上已完成轮次，但 Java 的 UnifiedChatRequest 没有这个字段，
 *     历史以数据库为准。不要把它当成模型看到的上下文。
 */
export const sendMessageStream = async (data: {
  message: string
  conversation_id: number | null
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
  mode?: 'auto' | 'plan' | 'resource' | 'exercise'
  images?: string[]
  /** 本轮图片对应的 file_info.id，后端据此把图片持久化到消息表（预签名 URL 会过期） */
  image_file_ids?: number[]
  style?: 'standard' | 'socratic'
}, signal?: AbortSignal): Promise<ReadableStream> => {
  console.log('[SSE] 准备发送请求:', {
    url: `${import.meta.env.VITE_API_BASE_URL || '/api'}/api/chat`,
    message: data.message.length > 50 ? data.message.substring(0, 50) + '...' : data.message,
    conversation_id: data.conversation_id,
    history_turns: data.messages.length
  })
  
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(data),
    signal,
  })
  
  console.log('[SSE] 请求完成，状态码:', response.status)
  
  // 检查 HTTP 状态码
  if (!response.ok) {
    const errorText = await response.text()
    console.error('[SSE] HTTP 错误:', { status: response.status, errorText })
    throw new ChatStreamError(messageForStatus(response.status), null, `HTTP_${response.status}`)
  }
  
  // 检查响应类型是否为 SSE
  const contentType = response.headers.get('content-type')
  console.log('[SSE] 响应 Content-Type:', contentType)
  
  if (!contentType || !contentType.includes('text/event-stream')) {
    console.error('[SSE] 响应类型错误，期望 text/event-stream')
    throw new Error('Expected text/event-stream response')
  }
  
  if (!response.body) {
    console.error('[SSE] 响应体为空')
    throw new Error('Response body is null')
  }
  
  console.log('[SSE] 开始流式传输')
  return response.body
}

/**
 * 把「结构化产物」帧渲染成 Markdown 正文。
 *
 * 背景：计划 / 出题 / 资源等中心**不发 token 流**，产物随收尾 `content` 帧
 * 一次性下发（`data.questions` 等）。前端正文通道只有字符串，
 * 故在此把结构化数据格式化成 Markdown，交由消息气泡按 Markdown 渲染。
 *
 * 当前支持 `questions`（出题中心）。返回空串表示该帧没有可渲染的产物。
 */
const formatStructuredContent = (payload: Record<string, unknown>): string => {
  const questions = payload.questions
  if (!Array.isArray(questions) || questions.length === 0) return ''

  const stem: string[] = []
  const answers: string[] = []
  const summary = typeof payload.response === 'string' ? payload.response.trim() : ''
  if (summary) stem.push(summary, '')

  questions.forEach((raw, index) => {
    if (!raw || typeof raw !== 'object') return
    const q = raw as Record<string, unknown>
    const text = String(q.question ?? q.content ?? '').trim()

    stem.push(`**第 ${index + 1} 题**`, '')
    if (text) stem.push(text, '')

    // options 形如 { A: '...', B: '...' }；简答/代码题可能为 null
    const options = q.options
    if (options && typeof options === 'object' && !Array.isArray(options)) {
      for (const [key, value] of Object.entries(options as Record<string, unknown>)) {
        if (value === null || value === undefined) continue
        stem.push(`- **${key}.** ${String(value)}`)
      }
      stem.push('')
    }

    const answer = q.correct_answer ?? q.answer
    const explanation = q.explanation
    const answerText = answer === null || answer === undefined ? '' : String(answer).trim()
    const explainText = explanation === null || explanation === undefined ? '' : String(explanation).trim()
    if (answerText || explainText) {
      answers.push(`**第 ${index + 1} 题**`, '')
      if (answerText) answers.push(`**答案：** ${answerText}`, '')
      if (explainText) answers.push(explainText, '')
    }
  })

  // 题目与答案分段：便于先自测、再对答案
  if (answers.length) {
    stem.push('---', '', '**参考答案**', '', ...answers)
  }
  return stem.join('\n').trim()
}

/**
 * 解析SSE流（支持新格式）
 * 新格式示例：
 * data:{"type": "token", "content": "哈哈"}
 * data:{"type": "done", "domain": "general", "conversation_id": 22}
 * 终态合同：error 与 done 都结束这一轮的正文回调（onError 之后不再 onDone）。
 * error 帧上的 conversation_id 通过 ChatStreamError 和 onConversationId 交出去，
 * 这样失败也不会丢掉当前会话。retract 只清空已流出的正文，不是终态。
 * 流在无终态事件下关闭时补一次 onDone，保证调用方状态一定收敛。
 * @param stream - 数据流
 * @param onData - 数据回调
 * @param onDone - 完成回调，参数为后端返回的会话 ID；没有会话 ID 时为 null
 * @param onError - 错误回调
 * @param onProgress - 进度回调（阶段 D）：后端 `progress` 事件表示"正在执行某步骤"，
 *   只用于展示**进度文案**；**绝不可**当作正文追加（正文只来自 token/content 事件）。
 * @param onVisualization - 结构化 UI block 回调（T004）：后端 `visualization` 事件
 *   形状为 `{type:'visualization', data:{type,version,props}}`，经 `dispatchUiBlock`
 *   完整校验（envelope + 类型注册 + props）后把结果原样交给上层：
 *   合法 → `{ok:true, component, props}`（上层渲染到对应消息下方）；
 *   非法 → `{ok:false, error}`（上层显示轻量降级提示）。
 *   与 progress 一样**绝不混入正文**，且 dispatchUiBlock 对任意输入不抛异常。
 */
export const parseSSEStream = async (
  stream: ReadableStream,
  onData: (delta: string, mode: string) => void,
  onDone: (conversationId: number | null) => void,
  onError?: (error: Error) => void,
  onProgress?: (progress: {
    stage: string
    message: string
    phase: string
  }) => void,
  onVisualization?: (block: DispatchResult) => void,
  hooks?: SseStreamHooks,
) => {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8') // 处理中文必须指定utf-8
  let buffer = '' // 用来粘包/拆包的缓冲区
  let terminated = false // 已触发 error/done 终态回调
  let knownConversationId: number | null = null
  const noteConversation = (value: unknown) => {
    if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) return
    if (knownConversationId === value) return
    knownConversationId = value
    hooks?.onConversationId?.(value)
  }
  /**
   * 当前 center 是否已经送出过正文（token 或 content）。
   *
   * 用途：判断「收尾 content 帧（partial=true）」是否为重复内容。
   * 后端只有 auto/tutor 路径逐字发 token；出题（exercise）、计划、资源
   * 等中心 **不产生 token**，其收尾帧就是本轮**唯一**正文载体。
   * 若不区分一律跳过，这些中心会整轮空白（表现为"后端没有返回任何内容"）。
   */
  let hasStreamedText = false

  console.log('[SSE] 开始解析数据流')

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log('[SSE] 数据流读取完成')
        break
      }

      // 1. 把Uint8Array解码成字符串，追加到缓冲区
      buffer += decoder.decode(value, { stream: true })
      // console.log('[SSE] 解码内容:', buffer.length > 200 ? buffer.substring(0, 200) + '...' : buffer)

      // 2. 按 SSE 事件分隔符拆分完整消息。
      //    SSE 规范（W3C EventSource）允许三种行尾：CRLF / LF / CR，
      //    故事件分隔符有 \r\n\r\n、\n\n、\r\r 三种形态。
      //    仅按 '\n\n' 切会漏掉本服务实际下发的 '\r\n\r\n'
      //    —— 那样整条响应会被当成一个残包，JSON 解析失败后全部丢弃，
      //    表现为「后端没有返回任何内容」。
      //
      //    归一化只对**确定完整**的部分做：网络分片可能把 \r\n 切在两个
      //    chunk 之间（尾部孤立 \r），故先把尾部 \r 留在缓冲区，下一轮再处理。
      const tailCR = buffer.endsWith('\r')
      const normalized = (tailCR ? buffer.slice(0, -1) : buffer).replace(/\r\n/g, '\n')
      const messages = normalized.split('\n\n')
      // 最后一段可能不完整，留在下一轮处理
      buffer = (messages.pop() || '') + (tailCR ? '\r' : '')

      // 3. 逐条处理消息
      for (const msg of messages) {
        if (!msg.trim()) continue

        // 提取data字段（支持多行data）
        const lines = msg.split('\n')
        let dataStr = ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            dataStr += line.substring(6)
          } else if (line.startsWith('data:')) {
            dataStr += line.substring(5)
          }
        }

        if (!dataStr) {
          console.log('[SSE] 非 data 行，跳过:', msg.substring(0, 50))
          continue
        }

        // console.log('[SSE] 提取到 data:', dataStr)

        // 4. 解析JSON业务数据
        try {
          const data = JSON.parse(dataStr)
          // console.log('[SSE] 收到业务数据:', data)

          // 按业务逻辑处理不同type
          switch (data.type) {
            case 'content': {
              // 后端统一事件：正文在 data.data.response / data.data.content / data.data（字符串）
              const payload = data.data
              const isPartial =
                !!payload && typeof payload === 'object' && (payload as Record<string, unknown>).partial === true

              // partial=true 的收尾帧：**仅当本轮已逐字送出过正文时**才跳过
              // （否则会重复渲染）。出题 / 计划 / 资源等中心不发 token，
              // 其收尾帧就是唯一正文，必须渲染，否则整轮空白。
              if (isPartial && hasStreamedText) {
                break
              }
              if (typeof payload === 'string' && payload) {
                hasStreamedText = true
                onData(payload, data.mode || 'chat')
              } else if (payload && typeof payload === 'object') {
                const record = payload as Record<string, unknown>
                // 结构化产物（如 questions）优先：formatStructuredContent 内部
                // 已把 response 摘要并进正文，故命中时不再单独追加 text。
                const structured = formatStructuredContent(record)
                const text = record.response ?? record.content
                const plain = typeof text === 'string' ? text.trim() : ''
                const rendered = structured || plain
                if (rendered) {
                  hasStreamedText = true
                  onData(rendered, data.mode || 'chat')
                }
              }
              break
            }
            case 'token':
              // 逐字追加文本
              if (data.content) {
                // console.log('[SSE] token 内容:', data.content)
                hasStreamedText = true
                onData(data.content, data.mode || 'chat')
              }
              break
            case 'inquiry': {
              // 后端追问：问题文本是本轮唯一合法产出，渲染出来避免空答案
              const question = data.message || data.content || data.data?.question
              if (typeof question === 'string' && question) {
                hasStreamedText = true
                onData(question, 'chat')
              }
              break
            }
            case 'progress':
              // 阶段 D：执行进度（后端 stage=节点名；不掺正文）
              if (onProgress) {
                onProgress({
                  stage: typeof data.stage === 'string' ? data.stage : '',
                  message: typeof data.message === 'string' ? data.message : '',
                  phase:
                    typeof data.data?.phase === 'string' ? data.data.phase : '',
                })
              }
              break
            case 'visualization':
              // T004：结构化 UI block 独立下发（payload 形状 {type,version,props}，
              // 后端在最终正文下发前已剥离对应围栏）。dispatchUiBlock 做完整校验，
              // 任意输入都不抛异常；结果原样交给上层（合法渲染 / 非法降级），
              // 绝不混入 onData 正文、不影响 hasStreamedText 的收尾帧判定。
              if (onVisualization) {
                onVisualization(dispatchUiBlock(data.data))
              }
              break
            case 'meta':
              noteConversation(data.conversation_id)
              break
            case 'retract':
              hasStreamedText = false
              hooks?.onRetract?.()
              break
            case 'recommendation': {
              const record = data.data && typeof data.data === 'object'
                ? data.data as Record<string, unknown>
                : {}
              const nodeName = typeof record.node_name === 'string' ? record.node_name : ''
              const label = typeof data.message === 'string' && data.message
                ? data.message
                : nodeName ? `要不要练一下「${nodeName}」？` : ''
              if (label) {
                hooks?.onRecommendation?.({
                  label,
                  prompt: nodeName ? `请出一组关于「${nodeName}」的练习` : label,
                })
              }
              break
            }
            case 'done':
              console.log('[SSE] 流结束:', data)
              terminated = true
              noteConversation(data.conversation_id)
              onDone(knownConversationId)
              return
            case 'error': {
              // 错误结束这一轮正文，不再把后面的 done 当成成功回调。
              // 会话 id 已经在错误对象里，调用方可以钉住当前会话。
              console.error('[SSE] 流异常:', data.code || data.content || data.message)
              terminated = true
              noteConversation(data.conversation_id)
              if (onError) {
                const content = typeof data.content === 'string' ? data.content : ''
                const message = typeof data.message === 'string' ? data.message : ''
                onError(new ChatStreamError(
                  content || message || USER_RETRY,
                  knownConversationId,
                  typeof data.code === 'string' ? data.code : null,
                ))
              }
              return
            }
            default:
              // 兼容旧格式
              if (data.delta || data.content) {
                console.log('[SSE] 兼容格式:', data.delta || data.content)
                onData(data.delta || data.content, data.mode || 'chat')
              }
          }
        } catch (e) {
          // 非JSON数据（比如纯文本）直接处理；
          // 但事件形状的残包（截断的 {...）不得当正文渲染
          if (dataStr.trim().startsWith('{')) {
            console.warn('[SSE] 丢弃无法解析的事件残包:', dataStr.substring(0, 80))
          } else {
            console.log('[SSE] 收到纯文本数据:', dataStr)
            onData(dataStr, 'chat')
          }
        }
      }
    }

    // 流结束：未收到任何终态事件时补一次 done，保证调用方状态收敛
    if (!terminated) {
      console.log('[SSE] 流式传输完成（未收到显式 done，本地收敛）')
      onDone(null)
    }
  } catch (error) {
    console.error('[SSE] 流式传输发生错误:', error)
    if (!terminated && onError) {
      onError(error as Error)
    }
  } finally {
    console.log('[SSE] 释放读取器锁')
    reader.releaseLock()
  }
}

/**
 * 发送消息
 * @param data - 消息数据
 */
export const sendMessage = (data: {
  userId: string
  content: string
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
