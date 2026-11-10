import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ContentBlockRenderer from './ContentBlockRenderer.vue'

describe('ContentBlockRenderer', () => {
  it('renders section, callout and code as text', () => {
    const wrapper = mount(ContentBlockRenderer, {
      props: {
        block: { type: 'section', heading: '概念', content: '<script>alert(1)</script>' },
      },
    })

    expect(wrapper.text()).toContain('概念')
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    expect(wrapper.find('[data-generated-html]').exists()).toBe(false)
  })

  it('renders unknown blocks without crashing', () => {
    const wrapper = mount(ContentBlockRenderer, {
      props: { block: { type: 'future_block', content: '暂不支持' } },
    })

    expect(wrapper.text()).toContain('暂不支持')
  })
})
