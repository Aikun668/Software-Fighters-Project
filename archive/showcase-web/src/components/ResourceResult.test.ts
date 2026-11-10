import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ResourceResult from './ResourceResult.vue'

describe('ResourceResult', () => {
  it('renders blocks in the supplied order', () => {
    const wrapper = mount(ResourceResult, {
      props: {
        topic: '反向传播',
        response: '已生成课程资料。',
        blocks: [
          { type: 'section', heading: '第一节', content: '先理解梯度。' },
          { type: 'callout', heading: '提醒', content: '注意链式法则。' },
        ],
      },
    })

    expect(wrapper.text().indexOf('第一节')).toBeLessThan(wrapper.text().indexOf('提醒'))
    expect(wrapper.text()).toContain('已生成课程资料。')
  })

  it('shows an unavailable message when there are no blocks', () => {
    const wrapper = mount(ResourceResult, {
      props: { topic: '反向传播', response: '', blocks: [] },
    })

    expect(wrapper.text()).toContain('暂时没有可展示的资源内容')
  })
})
