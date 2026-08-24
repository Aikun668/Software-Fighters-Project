import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { DonePayload } from '@/types/resource'
import { generateResource } from '@/api/resourceSse'
import ResourceWorkbenchView from './ResourceWorkbenchView.vue'

vi.mock('@/api/resourceSse', () => ({
  generateResource: vi.fn(),
}))

const donePayload: DonePayload = {
  content_blocks: [
    { type: 'section', heading: '核心概念', content: '这是课程内容。' },
  ],
  questions: [],
  response: '已生成课程资料。',
  error: '',
  review_status: 'pass',
  repair_attempted: false,
  fallback_used: false,
  final_status: 'success',
}

describe('ResourceWorkbenchView', () => {
  it('shows stages and the final result after done', async () => {
    vi.mocked(generateResource).mockImplementation(async (_request, onEvent) => {
      onEvent({ type: 'stage_start', stage: 'plan', message: '正在规划' })
      onEvent({ type: 'stage_end', stage: 'plan', message: '规划完成' })
      return donePayload
    })

    const wrapper = mount(ResourceWorkbenchView)
    await wrapper.find('textarea').setValue('Transformer 自注意力')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('规划完成')
    expect(wrapper.text()).toContain('已生成课程资料。')
  })

  it('keeps the topic and shows an error when generation fails', async () => {
    vi.mocked(generateResource).mockRejectedValueOnce(new Error('服务暂不可用'))

    const wrapper = mount(ResourceWorkbenchView)
    await wrapper.find('textarea').setValue('反向传播')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.find('textarea').element.value).toBe('反向传播')
    expect(wrapper.text()).toContain('服务暂不可用')
  })
})
