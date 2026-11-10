import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('showcase app shell', () => {
  it('renders the workbench placeholder', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('AI 学习资源工作台')
  })
})
