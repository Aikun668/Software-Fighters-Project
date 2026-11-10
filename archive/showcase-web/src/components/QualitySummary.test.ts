import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import QualitySummary from './QualitySummary.vue'

describe('QualitySummary', () => {
  it.each([
    ['pass', false, false, '已完成质量检查'],
    ['repair', false, false, '发现可改进项，当前保留原结果'],
    ['skipped', false, false, '质量评审暂不可用'],
    ['pass', true, false, '已执行一次受限修复'],
    ['pass', false, true, '已使用兼容的课程资料结果'],
  ] as const)('maps %s to truthful copy', (reviewStatus, repairAttempted, fallbackUsed, expectedText) => {
    const wrapper = mount(QualitySummary, {
      props: {
        reviewStatus,
        repairAttempted,
        fallbackUsed,
        finalStatus: 'success',
      },
    })

    expect(wrapper.text()).toContain(expectedText)
  })

  it('shows an incomplete state when final status is not success', () => {
    const wrapper = mount(QualitySummary, {
      props: {
        reviewStatus: 'pass',
        repairAttempted: false,
        fallbackUsed: false,
        finalStatus: 'error',
      },
    })

    expect(wrapper.text()).toContain('生成未完成')
  })
})
