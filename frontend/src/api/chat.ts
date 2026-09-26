import api from '@/utils/request'

/**
 * 发送消息（SSE流式）
 * @param data - 消息数据
 *   - messages: 已完成的对话历史（role/content 对），**不含当前 message**——
 *     后端 /api/chat 会把 message 追加为最后一条用户消息，前端重复传会出现两次。
 *     空 content 的 assistant 气泡（流式中/出错无正文）不得进入。
 */
export const sendMessageStream = async (data: {
  message: string
  conversation_id: number | null
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
}): Promise<ReadableStream> => {
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
    body: JSON.stringify(data)
  })
  
  console.log('[SSE] 请求完成，状态码:', response.status)
  
  // 检查 HTTP 状态码
  if (!response.ok) {
    const errorText = await response.text()
    console.error('[SSE] HTTP 错误:', { status: response.status, errorText })
    throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
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
 * 解析SSE流（支持新格式）
 * 新格式示例：
 * data:{"type": "token", "content": "哈哈"}
 * data:{"type": "done", "domain": "general", "conversation_id": 22}
 * 终态合同：error 与 done 均为唯一终态——任一触发后立即停止，
 * 不再触发后续回调（onError 之后不得再 onDone，反之亦然）；
 * 流在无终态事件下关闭时补一次 onDone，保证调用方状态一定收敛。
 * @param stream - 数据流
 * @param onData - 数据回调
 * @param onDone - 完成回调
 * @param onError - 错误回调
 * @param onProgress - 进度回调（阶段 D）：后端 `progress` 事件表示"正在执行某步骤"，
 *   只用于展示**进度文案**；**绝不可**当作正文追加（正文只来自 token/content 事件）。
 */
export const parseSSEStream = async (
  stream: ReadableStream,
  onData: (delta: string, mode: string) => void,
  onDone: () => void,
  onError?: (error: Error) => void,
  onProgress?: (progress: {
    stage: string
    message: string
    phase: string
  }) => void
) => {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8') // 处理中文必须指定utf-8
  let buffer = '' // 用来粘包/拆包的缓冲区
  let terminated = false // 已触发 error/done 终态回调

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

      // 2. 按SSE分隔符 \n\n 拆分完整消息
      const messages = buffer.split('\n\n')
      // 最后一段可能不完整，留在下一轮处理
      buffer = messages.pop() || ''

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
              // partial=true 表示 token 流已逐字送完，最终事件只是结构化收尾，
              // 不要重复追加文本（避免后端 _result_to_event 再渲染一次完整文本）
              if (payload && typeof payload === 'object' && payload.partial === true) {
                break
              }
              if (typeof payload === 'string' && payload) {
                onData(payload, data.mode || 'chat')
              } else if (payload && typeof payload === 'object') {
                const text = payload.response ?? payload.content
                if (typeof text === 'string' && text) {
                  onData(text, data.mode || 'chat')
                }
              }
              break
            }
            case 'token':
              // 逐字追加文本
              if (data.content) {
                // console.log('[SSE] token 内容:', data.content)
                onData(data.content, data.mode || 'chat')
              }
              break
            case 'inquiry': {
              // 后端追问：问题文本是本轮唯一合法产出，渲染出来避免空答案
              const question = data.message || data.content || data.data?.question
              if (typeof question === 'string' && question) {
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
            case 'done':
              console.log('[SSE] 流结束:', data)
              terminated = true
              onDone()
              return
            case 'error': {
              // 错误也是终态：触发 onError 后立即停止，后续 done 不再触发 onDone
              console.error('[SSE] 流异常:', data.content || data.message)
              terminated = true
              if (onError) {
                onError(new Error(data.content || data.message || 'Unknown error'))
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
      onDone()
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