import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

/**
 * 操作条的「不支持 TTS」分支。
 *
 * 必须是**独立文件**：`useSpeech.ts` 的 `supported` 是模块级常量，导入时就定型，
 * 无法在同一文件里既测支持又测不支持。jsdom 默认不实现 Web Speech API，
 * 所以这里只要不装桩，就等于「浏览器没有语音合成」。
 *
 * 这组用例锁的是一个真实回归风险：早期版本用 `supported` 控制整条操作条，
 * 结果在不支持 TTS 的环境里连复制按钮都一起没了。
 */

const { useSpeech } = await import('@/composables/useSpeech')
const MessageActions = (await import('../MessageActions.vue')).default
const ChatThread = (await import('../ChatThread.vue')).default

const mountActions = (props: Record<string, unknown> = {}) =>
  mount(MessageActions, { props: { messageId: 'a-1', text: '一段回答。', ...props } })

beforeEach(() => {
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  Object.defineProperty(document, 'execCommand', { value: undefined, configurable: true })
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('环境确实没有 Web Speech API（前提校验）', () => {
  it('useSpeech.supported 为 false', () => {
    expect(useSpeech().supported).toBe(false)
  })
})

describe('MessageActions：不支持朗读时只留复制', () => {
  it('不渲染朗读按钮', () => {
    const wrapper = mountActions()
    const labels = wrapper.findAll('.action-btn').map((b) => b.attributes('aria-label'))
    expect(labels).not.toContain('朗读')
  })

  it('复制按钮照常渲染且可用', async () => {
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })

    const wrapper = mountActions({ text: '**原文**保留' })
    const button = wrapper.get('.copy-btn')

    await button.trigger('click')
    await flushPromises()

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(button.attributes('aria-label')).toBe('已复制')
  })
})

describe('ChatThread：操作条不因缺少 TTS 而整体消失', () => {
  it('助手消息下仍渲染出复制按钮', () => {
    const wrapper = mount(ChatThread, {
      props: {
        conversationStarted: true,
        resourceMode: false,
        messages: [{ id: 'a-1', role: 'assistant', content: '普通回答' }],
        progressText: '',
      },
    })
    expect(wrapper.find('.message-actions').exists()).toBe(true)
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('复制')
  })
})
