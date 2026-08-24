import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ResourceInputPanel from './ResourceInputPanel.vue'

describe('ResourceInputPanel', () => {
  it('does not emit when the topic is blank', async () => {
    const wrapper = mount(ResourceInputPanel)

    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请输入想学习的主题')
  })

  it('emits the topic and selected resource type', async () => {
    const wrapper = mount(ResourceInputPanel)

    await wrapper.find('textarea').setValue('CNN 的卷积层')
    await wrapper.find('[data-resource-type="interactive_diagram"]').trigger('click')
    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({
      topic: 'CNN 的卷积层',
      resourceType: 'interactive_diagram',
    })
  })

  it('disables submission while streaming', () => {
    const wrapper = mount(ResourceInputPanel, { props: { disabled: true } })

    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })
})
