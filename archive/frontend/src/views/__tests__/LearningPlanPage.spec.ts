import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LearningPlanPage from '../LearningPlanPage.vue'

const { getLearningSnapshotMock, updatePlanProgressMock, routerPushMock, routeQuery } = vi.hoisted(() => ({
  getLearningSnapshotMock: vi.fn(),
  updatePlanProgressMock: vi.fn(),
  routerPushMock: vi.fn(),
  routeQuery: {
    courseId: 'ai_intro',
    nodeId: 'ml-basics',
    stepId: '7',
    actionKind: 'resume_plan',
    source: 'learning_snapshot',
  } as Record<string, string>,
}))

vi.mock('@/api/learningSnapshot', () => ({
  getLearningSnapshot: (...args: unknown[]) => getLearningSnapshotMock(...args),
}))

vi.mock('@/api/plans', () => ({
  updatePlanProgress: (...args: unknown[]) => updatePlanProgressMock(...args),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
  useRoute: () => ({ query: routeQuery }),
}))

const snapshot = {
  course_id: 'ai_intro',
  active_plan: {
    plan_id: 42,
    title: 'AI 工程师学习路径',
    status: 'in_progress',
    interrupted: true,
    current_step: { step_id: 7, order: 2, topic: '模型评估', node_id: 'ml-basics', status: 'in_progress' },
  },
  current_node: { node_id: 'ml-basics', name: '模型评估', reason: 'current_step_node' },
  next_action: null,
  freshness: { stale: false, missing_sources: [], computed_from: ['active_plan'] },
}

beforeEach(() => {
  getLearningSnapshotMock.mockReset()
  updatePlanProgressMock.mockReset()
  routerPushMock.mockReset()
  Object.assign(routeQuery, {
    courseId: 'ai_intro',
    nodeId: 'ml-basics',
    stepId: '7',
    actionKind: 'resume_plan',
    source: 'learning_snapshot',
  })
})

describe('LearningPlanPage 学习入口真实动作', () => {
  it('承接 resume_plan 上下文并调用真实计划 progress 接口，成功后返回学情入口', async () => {
    getLearningSnapshotMock.mockResolvedValue(snapshot)
    updatePlanProgressMock.mockResolvedValue({ status: 'completed', message: '步骤已完成' })

    const wrapper = mount(LearningPlanPage)
    await flushPromises()

    expect(wrapper.text()).toContain('模型评估')
    expect(wrapper.find('[data-test="complete-learning-action"]').exists()).toBe(true)

    await wrapper.find('[data-test="complete-learning-action"]').trigger('click')
    await flushPromises()

    expect(updatePlanProgressMock).toHaveBeenCalledWith(42, {
      step_id: 7,
      step_order: 2,
      status: 'completed',
      activity_type: 'study',
      score: 1,
      duration_minutes: 0,
    })
    expect(routerPushMock).toHaveBeenCalledWith({
      path: '/learning-analysis',
      query: { courseId: 'ai_intro', progressStatus: '步骤已完成' },
    })
  })

  it('review_current_node 使用 review 动作类型而不是只切换本地 checkbox', async () => {
    Object.assign(routeQuery, { actionKind: 'review_current_node', stepId: '' })
    getLearningSnapshotMock.mockResolvedValue(snapshot)
    updatePlanProgressMock.mockResolvedValue({ status: 'completed' })

    const wrapper = mount(LearningPlanPage)
    await flushPromises()
    await wrapper.find('[data-test="complete-learning-action"]').trigger('click')
    await flushPromises()

    expect(updatePlanProgressMock).toHaveBeenCalledWith(42, expect.objectContaining({
      step_id: 7,
      activity_type: 'review',
    }))
  })
})
