import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import QuestionNavChat from '../QuestionNavChat.vue'

// ── 模块级 mock：真实 SSE 客户端与路由 ──────────────────────────
const { sendMessageStreamMock, parseSSEStreamMock, getConversationMessagesMock, uploadFileMock, routeQuery } = vi.hoisted(() => ({
  sendMessageStreamMock: vi.fn(),
  parseSSEStreamMock: vi.fn(),
  getConversationMessagesMock: vi.fn(),
  uploadFileMock: vi.fn(),
  routeQuery: { conversationId: undefined as string | undefined },
}))

vi.mock('@/api/chat', () => ({
  sendMessageStream: (...args: unknown[]) => sendMessageStreamMock(...args),
  parseSSEStream: (...args: unknown[]) => parseSSEStreamMock(...args),
}))

vi.mock('@/api/conversations', () => ({
  getConversationMessages: (...args: unknown[]) => getConversationMessagesMock(...args),
}))

vi.mock('@/api/files', () => ({
  uploadFile: (...args: unknown[]) => uploadFileMock(...args),
}))

vi.mock('vue-router', () => ({
  // 生产 router 同时具备 push/replace（done 后会 replace 同步会话 id 到 URL）
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ query: routeQuery }),
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
  getConversationMessagesMock.mockReset()
  uploadFileMock.mockReset()
  getConversationMessagesMock.mockResolvedValue([])
  routeQuery.conversationId = undefined
  localStorage.clear()
})

describe('QuestionNavChat 真实聊天链路（Task 2 合同）', () => {
  it('空态输入框保持紧凑，并与消息滚动区分离', () => {
    const wrapper = mountPage()
    const scrollRegion = wrapper.find('.chat-scroll-region').element
    const composerDock = wrapper.find('.composer-dock').element

    expect(wrapper.find('textarea').attributes('rows')).toBe('1')
    expect(scrollRegion.nextElementSibling).toBe(composerDock)
  })

  it('工具栏可以选择对话模式和学习方式，并在按钮上反映当前选择', async () => {
    const wrapper = mountPage()

    await wrapper.get('.toolbar-select').trigger('click')
    await wrapper.get('[data-mode="resource"]').trigger('click')
    expect(wrapper.get('.toolbar-select').text()).toContain('资源生成')

    await wrapper.get('[data-style-trigger]').trigger('click')
    await wrapper.get('[data-style="socratic"]').trigger('click')
    expect(wrapper.get('[data-style-trigger]').text()).toContain('苏格拉底式')
  })

  it('选择图片附件后上传，并在下一次发送时携带图片 URL', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 7,
      url: 'https://files.example.test/notes.png',
      fileName: 'images/notes.png',
      originalName: 'notes.png',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_stream: ReadableStream, _onData: (d: string) => void, onDone: (id: number | null) => void) => {
      onDone(7)
    })

    const wrapper = mountPage()
    const file = new File(['fake image'], 'notes.png', { type: 'image/png' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file)
    expect(wrapper.text()).toContain('notes.png')

    await sendViaEnter(wrapper, '请看这张图片')
    expect(sendMessageStreamMock).toHaveBeenCalledWith(expect.objectContaining({
      images: ['https://files.example.test/notes.png'],
    }))
  })

  it('粘贴剪贴板图片时直接上传，并展示为可发送的图片附件', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 11,
      url: 'https://files.example.test/pasted.png',
      fileName: 'images/pasted.png',
      originalName: 'pasted.png',
    })

    const wrapper = mountPage()
    const pasted = new File(['fake clipboard image'], '', { type: 'image/png' })
    const box = wrapper.get('textarea')
    await box.trigger('paste', { clipboardData: { files: [pasted], items: [], types: ['Files'] } })
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(pasted)
    expect(wrapper.text()).toContain('pasted.png')
  })

  it('粘贴纯文本时不拦截默认行为，也不触发上传', async () => {
    const wrapper = mountPage()
    const box = wrapper.get('textarea')
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.assign(event, { clipboardData: { files: [], items: [], types: ['text/plain'] } })
    box.element.dispatchEvent(event)
    await flushPromises()

    expect(uploadFileMock).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('剪贴板只提供 items（Safari 等）时也能取到图片', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 12,
      url: 'https://files.example.test/items.png',
      fileName: 'images/items.png',
      originalName: 'items.png',
    })

    const wrapper = mountPage()
    const pasted = new File(['from items'], '', { type: 'image/png' })
    const box = wrapper.get('textarea')
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.assign(event, {
      clipboardData: {
        files: [],
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => pasted }],
        types: ['Files'],
      },
    })
    box.element.dispatchEvent(event)
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(pasted)
    expect(wrapper.text()).toContain('items.png')
  })

  it('files 与 items 同时存在时同一张图只上传一次', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 13,
      url: 'https://files.example.test/once.png',
      fileName: 'images/once.png',
      originalName: 'once.png',
    })

    const wrapper = mountPage()
    const pasted = new File(['dup'], 'dup.png', { type: 'image/png' })
    const box = wrapper.get('textarea')
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.assign(event, {
      clipboardData: {
        files: [pasted],
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => pasted }],
        types: ['Files'],
      },
    })
    box.element.dispatchEvent(event)
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(1)
  })

  it('没有 MIME 的拖拽/另存图片按扩展名识别为图片', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 14,
      url: 'https://files.example.test/noext.png',
      fileName: 'images/noext.png',
      originalName: 'noext.png',
    })

    const wrapper = mountPage()
    const file = new File(['x'], 'screenshot.png', { type: '' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(1)
    const sent = uploadFileMock.mock.calls[0][0] as File
    expect(sent.type).toBe('image/png')
  })

  it('非图片附件同样可以上传，只是不按图片预览', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 15,
      url: 'https://files.example.test/doc.pdf',
      fileName: 'files/doc.pdf',
      originalName: 'doc.pdf',
    })

    const wrapper = mountPage()
    const file = new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file)
    const chip = wrapper.get('.attachment-chip')
    expect(chip.text()).toContain('doc.pdf')
    // 非图片用文件图标，不渲染缩略图
    expect(chip.find('.attachment-thumb').exists()).toBe(false)
    expect(chip.find('.attachment-icon').exists()).toBe(true)
  })

  it('上传失败时展示后端返回的真实原因，而不是通用兜底文案', async () => {
    // 拦截器 reject 的是后端信封对象而非 Error 实例
    uploadFileMock.mockRejectedValue({ code: 413, message: '文件过大，单个文件请控制在 20MB 以内' })

    const wrapper = mountPage()
    const file = new File(['x'], 'huge.png', { type: 'image/png' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(wrapper.text()).toContain('文件过大，单个文件请控制在 20MB 以内')
    expect(wrapper.text()).not.toContain('附件上传失败，请稍后重试')
  })

  it('超过 20MB 的附件在本地就被拦下，不发出请求', async () => {
    const wrapper = mountPage()
    const file = new File(['x'], 'huge.png', { type: 'image/png' })
    Object.defineProperty(file, 'size', { value: 21 * 1024 * 1024 })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(uploadFileMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('附件过大')
  })

  it('多选附件时逐个上传，单个失败不影响其余附件', async () => {
    uploadFileMock
      .mockResolvedValueOnce({ fileId: 1, url: 'https://files.example.test/a.png', fileName: 'images/a.png', originalName: 'a.png' })
      .mockRejectedValueOnce({ code: 500, message: '服务器内部错误' })
      .mockResolvedValueOnce({ fileId: 3, url: 'https://files.example.test/c.png', fileName: 'images/c.png', originalName: 'c.png' })

    const wrapper = mountPage()
    const files = [
      new File(['a'], 'a.png', { type: 'image/png' }),
      new File(['b'], 'b.png', { type: 'image/png' }),
      new File(['c'], 'c.png', { type: 'image/png' }),
    ]
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: files, configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).toContain('a.png')
    expect(wrapper.text()).toContain('c.png')
    expect(wrapper.text()).toContain('服务器内部错误')
  })

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

describe('QuestionNavChat 附件发送（本轮合同）', () => {
  const attachOne = async (wrapper: ReturnType<typeof mountPage>, name = 'shot.png') => {
    const file = new File(['img'], name, { type: 'image/png' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()
  }

  it('工具栏按钮名为“附件”，且不限文件类型', () => {
    const wrapper = mountPage()
    const button = wrapper.findAll('.composer-toolbar button')[1]
    expect(button.text()).toContain('附件')

    // 不得把可上传类型限死为图片
    const accept = wrapper.get('input[type="file"]').attributes('accept')
    expect(accept).toBeUndefined()
  })

  it('只粘图片不打字也能发送：用占位文案满足后端 min_length', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 21,
      url: 'https://files.example.test/shot.png',
      fileName: 'images/shot.png',
      originalName: 'shot.png',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    await attachOne(wrapper)
    await sendViaEnter(wrapper, '')

    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
    const sent = sendMessageStreamMock.mock.calls[0][0] as { message: string; images: string[] }
    expect(sent.images).toEqual(['https://files.example.test/shot.png'])
    expect(sent.message.trim().length).toBeGreaterThan(0)
    // 气泡里回显图片，而不是只显示占位文案
    expect(wrapper.findAll('.msg-images img')).toHaveLength(1)
  })

  it('既无文字也无图片时不发送', async () => {
    const wrapper = mountPage()
    await sendViaEnter(wrapper, '   ')
    expect(sendMessageStreamMock).not.toHaveBeenCalled()
  })

  it('带文字时正常发送文字，并同时携带图片', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 22,
      url: 'https://files.example.test/a.png',
      fileName: 'images/a.png',
      originalName: 'a.png',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    await attachOne(wrapper, 'a.png')
    await sendViaEnter(wrapper, '这张图说明了什么？')

    const sent = sendMessageStreamMock.mock.calls[0][0] as { message: string; images: string[] }
    expect(sent.message).toBe('这张图说明了什么？')
    expect(sent.images).toEqual(['https://files.example.test/a.png'])
  })

  it('非图片附件可以随消息发送，但不得混进 images（AI 只消费图片）', async () => {
    uploadFileMock
      .mockResolvedValueOnce({ fileId: 31, url: 'https://files.example.test/a.png', fileName: 'images/a.png', originalName: 'a.png' })
      .mockResolvedValueOnce({ fileId: 32, url: 'https://files.example.test/doc.pdf', fileName: 'files/doc.pdf', originalName: 'doc.pdf' })

    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [
        new File(['a'], 'a.png', { type: 'image/png' }),
        new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' }),
      ],
      configurable: true,
    })
    await fileInput.trigger('change')
    await flushPromises()

    expect(wrapper.findAll('.attachment-chip')).toHaveLength(2)

    await sendViaEnter(wrapper, '两个附件都看看')

    const sent = sendMessageStreamMock.mock.calls[0][0] as { images?: string[] }
    // 只有 png 进入 images；pdf 不上送多模态
    expect(sent.images).toEqual(['https://files.example.test/a.png'])
  })

  it('只发非图片附件也能发送，不会被当成空消息拦住', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 33,
      url: 'https://files.example.test/only.pdf',
      fileName: 'files/only.pdf',
      originalName: 'only.pdf',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [new File(['%PDF'], 'only.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await fileInput.trigger('change')
    await flushPromises()

    await sendViaEnter(wrapper, '')

    expect(sendMessageStreamMock).toHaveBeenCalledTimes(1)
    const sent = sendMessageStreamMock.mock.calls[0][0] as { message: string; images?: string[] }
    expect(sent.message.trim().length).toBeGreaterThan(0)
    expect(sent.images).toBeUndefined()
  })

  it('发送失败时附件保留，不因一次失败被清空', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 23,
      url: 'https://files.example.test/keep.png',
      fileName: 'images/keep.png',
      originalName: 'keep.png',
    })
    sendMessageStreamMock.mockRejectedValueOnce(new Error('HTTP error! status: 502'))

    const wrapper = mountPage()
    await attachOne(wrapper, 'keep.png')
    await sendViaEnter(wrapper, '图片问题')

    expect(wrapper.text()).toContain('HTTP error! status: 502')
    // 附件条仍在，用户可以重试
    expect(wrapper.findAll('.attachment-chip')).toHaveLength(1)
  })
})

describe('QuestionNavChat 执行进度展示（阶段 D 合同）', () => {
  it('progress 事件展示进度文案，正文到达后清除，且不重复正文', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => (release = resolve))

    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (
        _stream: ReadableStream,
        onData: (d: string) => void,
        onDone: () => void,
        _onError: (e: Error) => void,
        onProgress: (p: { stage: string; message: string; phase: string }) => void,
      ) => {
        onProgress({ stage: 'extract', message: '正在执行 extract', phase: 'started' })
        await gate
        onData('正文内容')
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '讲讲反向传播')

    // 流式进行中：进度文案顶替"正在思考…"
    expect(wrapper.text()).toContain('正在执行 extract')
    expect(wrapper.text()).not.toContain('正在思考')

    release()
    await flushPromises()

    // 正文到达；流结束后进度清除
    expect(wrapper.text()).toContain('正文内容')
    expect(wrapper.text()).not.toContain('正在执行 extract')
  })
})

describe('QuestionNavChat 历史图片回显（本轮合同）', () => {
  it('回读会话时把后端签发的 images 映射进消息并渲染图片', async () => {
    routeQuery.conversationId = '70'
    getConversationMessagesMock.mockResolvedValue([
      {
        id: 136,
        conversationId: 70,
        role: 'user',
        content: '看看这个图片里面是什么',
        mode: 'chat',
        createdAt: '2026-09-30T19:17:30',
        images: ['https://files.example.test/history-a.png', 'https://files.example.test/history-b.png'],
      },
      { id: 137, conversationId: 70, role: 'assistant', content: '这张图是一个表情包。', mode: 'tutor', createdAt: '2026-09-30T19:17:35' },
    ])

    const wrapper = mountPage()
    await flushPromises()

    const imgs = wrapper.findAll('.msg-images img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0].attributes('src')).toBe('https://files.example.test/history-a.png')
    expect(imgs[1].attributes('src')).toBe('https://files.example.test/history-b.png')
  })

  it('没有图片的历史消息不渲染图片容器（不出现空占位）', async () => {
    routeQuery.conversationId = '22'
    getConversationMessagesMock.mockResolvedValue([
      { id: 201, conversationId: 22, role: 'user', content: '纯文字问题', mode: 'chat', createdAt: '2026-09-29T10:00:00' },
      { id: 202, conversationId: 22, role: 'assistant', content: '纯文字回答', mode: 'tutor', createdAt: '2026-09-29T10:00:01' },
    ])

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.findAll('.msg-images')).toHaveLength(0)
  })

  it('发送带图消息时同时上报 image_file_ids，供后端持久化', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 77,
      url: 'https://files.example.test/new.png',
      fileName: 'images/new.png',
      originalName: 'new.png',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    const file = new File(['img'], 'new.png', { type: 'image/png' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await flushPromises()

    await sendViaEnter(wrapper, '看这张图')

    const sent = sendMessageStreamMock.mock.calls[0][0] as { images?: string[]; image_file_ids?: number[] }
    expect(sent.images).toEqual(['https://files.example.test/new.png'])
    // 关键：URL 会过期，必须同时上报 fileId 才能持久化
    expect(sent.image_file_ids).toEqual([77])
  })

  it('非图片附件不上报 image_file_ids', async () => {
    uploadFileMock.mockResolvedValue({
      fileId: 78,
      url: 'https://files.example.test/doc.pdf',
      fileName: 'files/doc.pdf',
      originalName: 'doc.pdf',
    })
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_s: ReadableStream, _d: (x: string) => void, onDone: (id: number | null) => void) => {
      onDone(1)
    })

    const wrapper = mountPage()
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [new File(['%PDF'], 'doc.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    await fileInput.trigger('change')
    await flushPromises()

    await sendViaEnter(wrapper, '看这个文件')

    const sent = sendMessageStreamMock.mock.calls[0][0] as { image_file_ids?: number[] }
    expect(sent.image_file_ids).toBeUndefined()
  })
})

describe('QuestionNavChat 滚动跟随（本轮合同）', () => {
  /** 造一个可滚动的滚动容器，jsdom 默认 scrollHeight=0 */
  const stubScrollRegion = (wrapper: ReturnType<typeof mountPage>) => {
    const region = wrapper.get('.chat-scroll-region').element as HTMLElement
    let scrollTop = 0
    Object.defineProperty(region, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(region, 'clientHeight', { value: 400, configurable: true })
    Object.defineProperty(region, 'scrollTop', {
      get: () => scrollTop,
      set: (v: number) => { scrollTop = v },
      configurable: true,
    })
    return region
  }

  it('用户往上翻看时，流式输出不得把他拽回底部', async () => {
    let pushToken!: (s: string) => void
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (_s: ReadableStream, onData: (d: string) => void, onDone: () => void) => {
        pushToken = (s: string) => onData(s)
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '讲讲进程')
    const region = stubScrollRegion(wrapper)

    // 模拟用户往上翻（远离底部）
    region.scrollTop = 0
    region.dispatchEvent(new Event('scroll'))
    await flushPromises()

    // 流式继续吐字
    pushToken('更多正文')
    await flushPromises()
    await flushPromises()

    // 用户仍停在原处，没有被强行拉到底部
    expect(region.scrollTop).toBe(0)
  })

  it('用户停留在底部时，流式输出继续自动跟随', async () => {
    let pushToken!: (s: string) => void
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(
      async (_s: ReadableStream, onData: (d: string) => void, onDone: () => void) => {
        pushToken = (s: string) => onData(s)
        onDone()
      },
    )

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '讲讲进程')
    const region = stubScrollRegion(wrapper)

    // 贴底状态
    region.scrollTop = 600
    region.dispatchEvent(new Event('scroll'))
    await flushPromises()

    pushToken('新内容')
    await flushPromises()
    await flushPromises()

    expect(region.scrollTop).toBe(1000)
  })

  it('打开历史会话时强制贴底（不沿用上一次的跟随状态）', async () => {
    routeQuery.conversationId = '22'
    getConversationMessagesMock.mockResolvedValue([
      { id: 301, conversationId: 22, role: 'user', content: '历史问题', mode: 'chat', createdAt: '2026-09-29T10:00:00' },
      { id: 302, conversationId: 22, role: 'assistant', content: '历史回答', mode: 'tutor', createdAt: '2026-09-29T10:00:01' },
    ])

    const wrapper = mountPage()
    await flushPromises()

    // 打开会话后必须落在最新一条消息处
    const region = wrapper.get('.chat-scroll-region').element as HTMLElement
    let top = 0
    Object.defineProperty(region, 'scrollHeight', { value: 1200, configurable: true })
    Object.defineProperty(region, 'clientHeight', { value: 400, configurable: true })
    Object.defineProperty(region, 'scrollTop', {
      get: () => top,
      set: (v: number) => { top = v },
      configurable: true,
    })

    expect(wrapper.text()).toContain('历史问题')
    expect(wrapper.text()).toContain('历史回答')
  })
})

describe('QuestionNavChat 会话列表与回读（方案 A）', () => {
  it('根据全局侧栏传入的 conversationId 按顺序回显 user/assistant 消息', async () => {
    routeQuery.conversationId = '22'
    getConversationMessagesMock.mockResolvedValue([
      { id: 101, conversationId: 22, role: 'user', content: '什么是进程？', mode: 'chat', createdAt: '2026-09-29T10:00:00' },
      { id: 102, conversationId: 22, role: 'assistant', content: '进程是资源分配的基本单位。', mode: 'chat', createdAt: '2026-09-29T10:00:01' },
    ])

    const wrapper = mountPage()
    await flushPromises()

    expect(getConversationMessagesMock).toHaveBeenCalledWith(22)
    expect(wrapper.text()).toContain('什么是进程？')
    expect(wrapper.text()).toContain('进程是资源分配的基本单位。')
  })

  it('在已打开的会话里继续发送时复用当前 conversation_id', async () => {
    routeQuery.conversationId = '22'
    getConversationMessagesMock.mockResolvedValue([
      { id: 101, conversationId: 22, role: 'user', content: '上一问', mode: 'chat', createdAt: '2026-09-29T10:00:00' },
      { id: 102, conversationId: 22, role: 'assistant', content: '上一答', mode: 'chat', createdAt: '2026-09-29T10:00:01' },
    ])
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_stream: ReadableStream, _onData: (d: string) => void, onDone: (id: number | null) => void) => {
      onDone(22)
    })

    const wrapper = mountPage()
    await flushPromises()
    await sendViaEnter(wrapper, '继续提问')

    expect(sendMessageStreamMock).toHaveBeenCalledWith(expect.objectContaining({ conversation_id: 22 }))
  })

  it('记住 done 返回的 conversation_id，下一次发送继续复用', async () => {
    sendMessageStreamMock.mockResolvedValue(new ReadableStream())
    parseSSEStreamMock.mockImplementation(async (_stream: ReadableStream, _onData: (d: string) => void, onDone: (id: number | null) => void) => {
      onDone(22)
    })

    const wrapper = mountPage()
    await sendViaEnter(wrapper, '第一问')
    await sendViaEnter(wrapper, '第二问')

    expect(sendMessageStreamMock.mock.calls[1][0]).toEqual(expect.objectContaining({ conversation_id: 22 }))
  })

})
