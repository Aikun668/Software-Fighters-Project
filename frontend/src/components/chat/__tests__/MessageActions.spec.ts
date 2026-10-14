import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

/**
 * jsdom 不实现 Web Speech API，必须在**导入被测模块之前**把桩装到 window 上：
 * `useSpeech.ts` 的 `supported` 是模块级常量，导入时就已定型。
 */

class FakeUtterance {
  text: string
  lang = ''
  voice: SpeechSynthesisVoice | null = null
  rate = 1
  pitch = 1
  volume = 1
  onend: (() => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  constructor(text: string) {
    this.text = text
  }
}

let spoken: FakeUtterance[] = []
let cancelCount = 0
let pauseCount = 0
let resumeCount = 0

const fakeVoices = [
  { lang: 'zh-CN', name: 'Fake Chinese', default: false, localService: true, voiceURI: 'zh' },
  { lang: 'en-US', name: 'Fake English', default: false, localService: true, voiceURI: 'en' },
] as SpeechSynthesisVoice[]

const speechSynthesisStub = {
  speak: (u: FakeUtterance) => spoken.push(u),
  cancel: () => { cancelCount += 1 },
  pause: () => { pauseCount += 1 },
  resume: () => { resumeCount += 1 },
  getVoices: () => fakeVoices,
  addEventListener: () => {},
  removeEventListener: () => {},
  speaking: false,
  paused: false,
  pending: false,
}

vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

// 被测模块在 supported 判定中同时检查 window.speechSynthesis 与 window.SpeechSynthesisUtterance
Object.defineProperty(window, 'speechSynthesis', { value: speechSynthesisStub, configurable: true })

const { __resetSpeechForTests, useSpeech } = await import('@/composables/useSpeech')
const MessageActions = (await import('../MessageActions.vue')).default

const mountActions = (props: Record<string, unknown>) =>
  mount(MessageActions, { props: { messageId: 'a-1', text: '这是一段回答。', ...props } })

/** 操作条里第二个按钮是「复制」，用类名精确定位，避免依赖按钮顺序 */
const copyButton = (wrapper: ReturnType<typeof mountActions>) => wrapper.get('.copy-btn')

/** 每个用例开始前把剪贴板收干净，避免上一个用例的桩泄漏进来 */
const resetClipboard = () => {
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  Object.defineProperty(document, 'execCommand', { value: undefined, configurable: true })
}

/** 装一个成功的 writeText 桩，返回 spy 供断言 */
const stubClipboardSuccess = () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  return writeText
}

beforeEach(() => {
  spoken = []
  cancelCount = 0
  pauseCount = 0
  resumeCount = 0
  __resetSpeechForTests()
  resetClipboard()
})

afterEach(() => {
  __resetSpeechForTests()
  resetClipboard()
  vi.useRealTimers()
})

describe('MessageActions：朗读按钮的显示条件', () => {
  it('正文非空时显示朗读按钮', () => {
    const wrapper = mountActions({})
    expect(wrapper.get('.action-btn').attributes('aria-label')).toBe('朗读')
  })

  it('流式输出中不显示（避免按钮闪烁）', () => {
    const wrapper = mountActions({ streaming: true })
    expect(wrapper.find('.action-btn').exists()).toBe(false)
  })

  it('正文为空时即使不在流式中也不显示', () => {
    const wrapper = mountActions({ text: '   ' })
    expect(wrapper.find('.action-btn').exists()).toBe(false)
  })
})

describe('MessageActions：点击朗读', () => {
  it('点击后开始朗读，并进入「暂停朗读」态', async () => {
    const wrapper = mountActions({ text: '第一句话。' })
    await wrapper.get('.action-btn').trigger('click')

    expect(spoken).toHaveLength(1)
    expect(spoken[0].text).toBe('第一句话。')
    // 中文内容应自动挂中文音色
    expect(spoken[0].lang).toBe('zh-CN')
    expect(spoken[0].voice?.lang).toBe('zh-CN')

    expect(wrapper.get('.action-btn').attributes('aria-label')).toBe('暂停朗读')
    expect(wrapper.get('.action-btn').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.action-btn').classes()).toContain('is-active')
  })

  it('再次点击变为暂停，第三次点击恢复', async () => {
    const wrapper = mountActions({ text: '第一句话。' })
    const button = wrapper.get('.action-btn')

    await button.trigger('click')
    expect(useSpeech().status.value).toBe('playing')

    await button.trigger('click')
    expect(pauseCount).toBe(1)
    expect(useSpeech().status.value).toBe('paused')
    expect(wrapper.get('.action-btn').attributes('aria-label')).toBe('继续朗读')

    await button.trigger('click')
    expect(resumeCount).toBe(1)
    expect(useSpeech().status.value).toBe('playing')
  })

  it('长文本被切成多块依次朗读（规避 Chrome 截断）', async () => {
    const long = '这是一句用来测试分块的长句子，需要重复很多次才能超过上限。'.repeat(8)
    const wrapper = mountActions({ text: long })

    await wrapper.get('.action-btn').trigger('click')
    // 首块立即开播，其余排队等待 onend
    expect(spoken).toHaveLength(1)
    expect(spoken[0].text.length).toBeLessThanOrEqual(120)

    // 模拟第一块播完 → 自动续播第二块
    spoken[0].onend?.()
    expect(spoken).toHaveLength(2)

    // 逐块播完后回到 idle
    while (spoken.length && spoken[spoken.length - 1].onend) {
      const last = spoken[spoken.length - 1]
      const before = spoken.length
      last.onend?.()
      if (spoken.length === before) break
    }
    expect(useSpeech().status.value).toBe('idle')
    expect(useSpeech().activeId.value).toBeNull()
  })

  it('朗读代码块时不会把代码念出来', async () => {
    const md = ['说明如下：', '```js', 'const a = 1;', '```', '以上。'].join('\n')
    const wrapper = mountActions({ text: md })
    await wrapper.get('.action-btn').trigger('click')

    expect(spoken[0].text).not.toContain('const a = 1')
    expect(spoken[0].text).toContain('说明如下')
  })

  it('纯英文内容自动切英文音色', async () => {
    const wrapper = mountActions({ text: 'This is a plain English answer about gradients.' })
    await wrapper.get('.action-btn').trigger('click')

    expect(spoken[0].lang).toBe('en-US')
    expect(spoken[0].voice?.lang).toBe('en-US')
  })
})

describe('MessageActions：复制按钮', () => {
  it('与朗读按钮并列渲染在同一操作条里', () => {
    const wrapper = mountActions({})
    expect(wrapper.findAll('.action-btn')).toHaveLength(2)
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('复制')
  })

  it('复制的是原始 Markdown 正文，而不是渲染后的 HTML', async () => {
    const writeText = stubClipboardSuccess()
    const raw = '# 标题\n\n**加粗**内容'
    const wrapper = mountActions({ text: raw })

    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(raw)
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('已复制')
    expect(wrapper.get('.copy-btn').classes()).toContain('is-done')
  })

  it('复制成功后反馈自动复位为「复制」', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    stubClipboardSuccess()
    const wrapper = mountActions({})

    await copyButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('已复制')

    vi.advanceTimersByTime(1600)
    await flushPromises()
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('复制')
  })

  it('连点复制只保留一个复位定时器，反馈不会被前一次提前抹掉', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    stubClipboardSuccess()
    const wrapper = mountActions({})
    const button = copyButton(wrapper)

    await button.trigger('click')
    await flushPromises()
    await button.trigger('click')
    await flushPromises()

    expect(vi.getTimerCount()).toBe(1)
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('已复制')
  })

  it('组件销毁时清掉复位定时器，避免在已卸载组件上改状态', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    stubClipboardSuccess()
    const wrapper = mountActions({})

    await copyButton(wrapper).trigger('click')
    await flushPromises()
    expect(vi.getTimerCount()).toBe(1)

    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('剪贴板不可用（局域网 http）时退到 execCommand，按钮仍显示成功', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })

    const wrapper = mountActions({})
    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('已复制')
  })

  it('两条路径都失败时显示「复制失败」，而不是假装成功', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('NotAllowedError')) },
      configurable: true,
    })
    // 降级路径也不可用（jsdom 默认没有 execCommand），整体应判失败
    const wrapper = mountActions({})

    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.get('.copy-btn').attributes('aria-label')).toBe('复制失败')
    expect(wrapper.get('.copy-btn').classes()).toContain('is-failed')
  })

  it('复制按钮不影响朗读：点复制不会开始发声', async () => {
    stubClipboardSuccess()
    const wrapper = mountActions({})

    await copyButton(wrapper).trigger('click')
    await flushPromises()

    expect(spoken).toHaveLength(0)
    expect(useSpeech().status.value).toBe('idle')
  })
})

describe('useSpeech：全局单例播放态', () => {
  it('播放另一条消息会打断当前这条', async () => {
    const first = mountActions({ messageId: 'a-1', text: '第一条回答。' })
    const second = mountActions({ messageId: 'a-2', text: '第二条回答。' })

    await first.get('.action-btn').trigger('click')
    expect(useSpeech().isPlaying('a-1')).toBe(true)

    // 首次播放自身也会 cancel 一次清理残留，所以这里比较增量
    const cancelsBefore = cancelCount
    await second.get('.action-btn').trigger('click')
    expect(cancelCount).toBe(cancelsBefore + 1)
    expect(useSpeech().isPlaying('a-1')).toBe(false)
    expect(useSpeech().isPlaying('a-2')).toBe(true)

    // 第一条的按钮回到初始态
    expect(first.get('.action-btn').attributes('aria-label')).toBe('朗读')
    expect(first.get('.action-btn').classes()).not.toContain('is-active')
  })

  it('组件销毁时若正在朗读本条则停止发声', async () => {
    const wrapper = mountActions({ messageId: 'a-1', text: '一段回答。' })
    await wrapper.get('.action-btn').trigger('click')
    expect(useSpeech().isPlaying('a-1')).toBe(true)

    wrapper.unmount()
    expect(useSpeech().activeId.value).toBeNull()
    expect(useSpeech().status.value).toBe('idle')
  })

  it('销毁其它消息的组件不会打断本条朗读', async () => {
    const playing = mountActions({ messageId: 'a-1', text: '正在播的回答。' })
    const other = mountActions({ messageId: 'a-2', text: '另一条回答。' })

    await playing.get('.action-btn').trigger('click')
    other.unmount()

    expect(useSpeech().isPlaying('a-1')).toBe(true)
  })

  it('切换消息后，旧消息迟到的 onend 不会跳掉新消息的内容', async () => {
    // 两条都要超过分块上限，才有多块可供"跳块"观察
    const longA = '这是第一条很长的回答内容，需要重复多次才能超过分块上限。'.repeat(8)
    const longB = '这是第二条很长的回答内容，同样需要重复多次超过上限。'.repeat(8)

    const first = mountActions({ messageId: 'a-1', text: longA })
    const second = mountActions({ messageId: 'a-2', text: longB })

    await first.get('.action-btn').trigger('click')
    const staleUtterance = spoken[0]

    await second.get('.action-btn').trigger('click')
    const countAfterSwitch = spoken.length // 第二条的首块已入队

    // 旧消息首块的 onend 现在才到达：必须被丢弃，不能推进第二条的进度
    staleUtterance.onend?.()
    expect(spoken).toHaveLength(countAfterSwitch)

    // 第二条自己的 onend 仍然正常工作（能续播下一块）
    spoken[countAfterSwitch - 1].onend?.()
    expect(spoken.length).toBe(countAfterSwitch + 1)
  })
})
