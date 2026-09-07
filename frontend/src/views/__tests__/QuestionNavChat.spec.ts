import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import QuestionNavChat from '../QuestionNavChat.vue'

// ── 模块级 mock：真实 SSE 客户端与路由 ──────────────────────────
const { sendMessageStreamMock, parseSSEStreamMock } = vi.hoisted(() => ({
  sendMessageStreamMock: vi.fn(),
  parseSSEStreamMock: vi.fn(),
}))

vi.mock('@/api/chat', () => ({
  sendMessageStream: (...args: unknown[]) => sendMessageStreamMock(...args),
  parseSSEStream: (...args: unknown[]) => parseSSEStreamMock(...args),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))

const mountPage = () =>
  mount(QuestionNavChat, {
    global: {
      config: { warnHandler: () => {} },
    },
  })

const sendViaEnter = async (wrapper: ReturnType<typeof mountPage>, text: string) => {
  const box = wrapper.find('textarea')
  await box.setValue(text)
  await box.trigger('keydown.enter.exact')
  await flushPromises()
}

beforeEach(() => {
  sendMessageStreamMock.mockReset()
  parseSSEStreamMock.mockReset()
  localStorage.clear()
})

describe('QuestionNavChat 真实聊天链路（Task 2 合同）', () => {
  it('发送后必须调用真实 SSE 客户端一次，并渲染 content 事件内容', async () => {
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (_stream: ReadableStream, onData: (d: string) => void, onDone: () => void) => {
        onData('进程是资源分配的基本单位。')
        onData('它包括程序代码与运行时的状态。')
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '什么是进程？')

    // 真实客户端被调用且仅一次
    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
    expect(sendMessageStreamMock).toHaveBeenCalledWith({
      message: '什么是进程？',
      conversation_id: null,
      messages: [],
    })
    // 客户端返回的流交给唯一 SSE 解析位置
    expect(parseSSEStreamMock).toHaveBeenCalledTimes(1)
    // 页面显示来自 content 事件的文本
    expect(wrapper.text()).toContain('进程是资源分配的基本单位。')
    expect(wrapper.text()).toContain('它包括程序代码与运行时的状态。')
    // 不再出现静态演示/模拟回答
    expect(wrapper.text()).not.toContain('静态演示')
  })

  it('请求失败时显示真实错误并允许重试，不得回退到本地回答', async () => {
    sendMessageStreamMock.mockRejectedValueOnce(new Error('HTTP error! status: 502'))

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '什么是进程？')

    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
    // 显示真实错误信息
    expect(wrapper.text()).toContain('HTTP error! status: 502')
    // 不出现任何伪造回答
    expect(wrapper.text()).not.toContain('好的，我来帮你解答')
    // 输入恢复可用：可以再次发送
    await sendViaEnter(wrapper, '再问一次')
    expect(sendMessageStreamMock).toHaveBeenCalledTimes(2)
  })

  it('流中途 error 事件要展示错误，且后续 done 不清掉错误', async () => {
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (
        _stream: ReadableStream,
        onData: (d: string) => void,
        onDone: () => void,
        onError: (e: Error) => void,
      ) => {
        onData('前面一半内容')
        onError(new Error('处理失败，请稍后重试'))
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '什么是进程？')

    expect(wrapper.text()).toContain('前面一半内容')
    expect(wrapper.text()).toContain('处理失败，请稍后重试')
  })

  it('空输入与发送中不允许重复提交', async () => {
    let release!: (v: unknown) => void
    sendMessageStreamMock.mockReturnValue(new Promise((resolve) => (release = resolve)))
    parseSSEStreamMock.mockResolvedValue(undefined)

    const wrapper = mountPage()
    // 空输入不发送
    await sendViaEnter(wrapper, '   ')
    expect(sendMessageStreamMock).not.toHaveBeenCalled()

    await sendViaEnter(wrapper, '什么是进程？')
    // streaming 期间再按回车不重复发送
    await sendViaEnter(wrapper, '第二个问题')
    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)

    release(new ReadableStream())
    await flushPromises()
  })
})

describe('QuestionNavChat 对话历史传输（Task 11 后续合同）', () => {
  it('第二次发送必须携带第一轮的用户与助手内容', async () => {
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (_stream: ReadableStream, onData: (d: string) => void, onDone: () => void) => {
        onData('第一轮的完整回答。')
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '第一问')
    await sendViaEnter(wrapper, '第二问')

    expect(sendMessageStreamMock).toHaveBeenCalledTimes(2)
    const [firstCall, secondCall] = sendMessageStreamMock.mock.calls.map(
      (call) => call[0] as { message: string; messages: Array<{ role: string; content: string }> },
    )
    // 首次发送历史为空
    expect(firstCall.messages).toEqual([])
    // 第二次发送携带第一轮完整问答对，且不含当前消息本身
    expect(secondCall.message).toBe('第二问')
    expect(secondCall.messages).toEqual([
      { role: 'user', content: '第一问' },
      { role: 'assistant', content: '第一轮的完整回答。' },
    ])
  })

  it('出错且无正文时，下一轮历史必须丢弃整组失败问答', async () => {
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (_stream: ReadableStream, onData: (d: string) => void, onDone: () => void) => {
        onData('正常的第二答。')
        onDone()
      },
    )

    const wrapper = mountPage()
    // 第一轮：请求直接失败，assistant 无正文
    sendMessageStreamMock.mockRejectedValueOnce(new Error('HTTP error! status: 502'))
    await sendViaEnter(wrapper, '第一问')

    // 第二轮：成功
    await sendViaEnter(wrapper, '第二问')
    // 第三轮
    await sendViaEnter(wrapper, '第三问')

    const thirdCall = sendMessageStreamMock.mock.calls[2][0] as {
      messages: Array<{ role: string; content: string }>
    }
    // 第三次发送的历史：第一轮没有可见回答，整组失败问答都不进；
    // 第二轮的正常问答对保留。
    expect(thirdCall.messages).toEqual([
      { role: 'user', content: '第二问' },
      { role: 'assistant', content: '正常的第二答。' },
    ])
  })
})
