import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatThread from '../ChatThread.vue'
import MessageActions from '../MessageActions.vue'
import type { ChatMessage } from '../chat-types'

/**
 * ChatThread 的正文渲染合同。
 *
 * 背景：本组件此前用 `{{ msg.content }}` 插值输出助手正文，导致大模型返回的
 * Markdown（`#` / `**` / 列表 / 代码块）被原样当字面文字显示。本轮改为
 * `v-html` + `marked` 渲染，并经 DOMPurify 清洗。
 *
 * 这组用例锁三件事：
 *   1. Markdown 真的被转成了 HTML 标签（而非字面文本）；
 *   2. 危险 HTML 被清洗掉（XSS 防护生效）；
 *   3. 朗读组件仍拿到**原始 Markdown 文本**（不能被 HTML 污染）。
 */

const mountThread = (messages: ChatMessage[]) =>
  mount(ChatThread, {
    props: {
      conversationStarted: true,
      resourceMode: false,
      messages,
      progressText: '',
    },
    global: { config: { warnHandler: () => {} } },
  })

const assistantMsg = (content: string, extra: Partial<ChatMessage> = {}): ChatMessage =>
  ({ id: 1, role: 'assistant', content, ...extra }) as ChatMessage

describe('ChatThread 助手正文 Markdown 渲染', () => {
  it('把 Markdown 标题转成 <h1> 标签，而不是显示字面井号', () => {
    const wrapper = mountThread([assistantMsg('# MinIO 是什么？')])
    expect(wrapper.find('.msg-markdown h1').exists()).toBe(true)
    expect(wrapper.find('.msg-markdown h1').text()).toBe('MinIO 是什么？')
    expect(wrapper.text()).not.toContain('# MinIO')
  })

  it('把 **加粗** 转成 <strong> 标签', () => {
    const wrapper = mountThread([assistantMsg('**高性能**对象存储')])
    expect(wrapper.find('.msg-markdown strong').exists()).toBe(true)
    expect(wrapper.find('.msg-markdown strong').text()).toBe('高性能')
    expect(wrapper.text()).not.toContain('**高性能**')
  })

  it('把无序列表转成 <ul>/<li>', () => {
    const wrapper = mountThread([assistantMsg('- 图片\n- 视频\n- 模型文件')])
    expect(wrapper.findAll('.msg-markdown li')).toHaveLength(3)
    expect(wrapper.text()).not.toContain('- 图片')
  })

  it('把代码块转成 <pre><code>', () => {
    const wrapper = mountThread([assistantMsg('```\nminio server /data\n```')])
    expect(wrapper.find('.msg-markdown pre code').exists()).toBe(true)
    expect(wrapper.find('.msg-markdown pre code').text()).toContain('minio server /data')
  })

  it('正文渲染在 .msg-markdown 容器内（样式钩子存在）', () => {
    const wrapper = mountThread([assistantMsg('普通一句话')])
    expect(wrapper.find('.msg-markdown').exists()).toBe(true)
  })
})

describe('ChatThread 的 XSS 防护（DOMPurify 必须生效）', () => {
  it('剥掉 <script> 标签', () => {
    const wrapper = mountThread([assistantMsg('安全内容<script>alert(1)</script>')])
    expect(wrapper.find('.msg-markdown script').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('alert(1)')
  })

  it('剥掉 <img onerror> 这类事件处理器', () => {
    const wrapper = mountThread([
      assistantMsg('<img src=x onerror="alert(1)">正文'),
    ])
    expect(wrapper.html()).not.toContain('onerror')
  })

  it('剥掉 javascript: 伪协议链接', () => {
    const wrapper = mountThread([assistantMsg('[点我](javascript:alert(1))')])
    expect(wrapper.html()).not.toContain('javascript:')
  })

  it('保留安全的 Markdown 结构（清洗不能过度）', () => {
    const wrapper = mountThread([assistantMsg('## 标题\n\n**粗体**与[正常链接](https://example.com)')])
    expect(wrapper.find('.msg-markdown h2').exists()).toBe(true)
    expect(wrapper.find('.msg-markdown strong').exists()).toBe(true)
    expect(wrapper.find('.msg-markdown a').attributes('href')).toBe('https://example.com')
  })
})

describe('ChatThread 朗读文本必须保持原始 Markdown', () => {
  it('MessageActions 收到的是原文，而不是渲染后的 HTML', () => {
    const raw = '# 标题\n\n**加粗**内容'
    const wrapper = mountThread([assistantMsg(raw, { streaming: false })])
    const actions = wrapper.findComponent(MessageActions)
    expect(actions.exists()).toBe(true)
    // 传下去的是 Markdown 原文：朗读不该念出 `#` 与 `**`，也不该拿到 HTML 标签
    expect(actions.props('text')).toBe(raw)
  })
})

describe('ChatThread 操作条的显示条件', () => {
  it('正常助手消息显示操作条', () => {
    const wrapper = mountThread([assistantMsg('一段回答')])
    expect(wrapper.find('.message-actions').exists()).toBe(true)
  })

  it('正文为空的助手消息不显示操作条', () => {
    const wrapper = mountThread([assistantMsg('   ')])
    expect(wrapper.find('.message-actions').exists()).toBe(false)
  })

  it('出错的消息不显示操作条（没有稳定正文可复制）', () => {
    const wrapper = mountThread([assistantMsg('部分内容', { error: '后端 500' })])
    expect(wrapper.find('.message-actions').exists()).toBe(false)
  })

  it('用户消息不显示操作条', () => {
    const wrapper = mountThread([{ id: 'u-1', role: 'user', content: '你好' }])
    expect(wrapper.find('.message-actions').exists()).toBe(false)
  })
})
