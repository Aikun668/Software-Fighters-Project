import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}))

vi.mock('@/utils/request', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
  },
}))

import { getLearningSnapshot } from '../learningSnapshot'

const snapshot = {
  student_id: 1,
  course_id: 'ai_intro',
  generated_at: '2026-09-28T08:51:49Z',
  active_plan: null,
  current_node: null,
  mastery: { node_id: null, value: null, level: 'unknown', source: 'none' },
  recent_evidence: [],
  freshness: { stale: false, missing_sources: [], computed_from: [] },
}

describe('getLearningSnapshot', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('解开 Java 结果里的 success/data 包装，返回真正的学习快照', async () => {
    getMock.mockResolvedValue({ success: true, data: snapshot })

    await expect(getLearningSnapshot('ai_intro')).resolves.toEqual(snapshot)
    expect(getMock).toHaveBeenCalledWith('/learning-snapshot', { courseId: 'ai_intro' })
  })

  it('也兼容已经是快照本体的响应', async () => {
    getMock.mockResolvedValue(snapshot)

    await expect(getLearningSnapshot('ai_intro')).resolves.toEqual(snapshot)
  })
})
