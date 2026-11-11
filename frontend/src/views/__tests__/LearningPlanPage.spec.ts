import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LearningPlanPage from '../LearningPlanPage.vue'

const { getLearningSnapshotMock, updatePlanProgressMock, routerPushMock, routeQuery, listAdaptivePlansMock } = vi.hoisted(() => ({
  getLearningSnapshotMock: vi.fn(),
  updatePlanProgressMock: vi.fn(),
  routerPushMock: vi.fn(),
  listAdaptivePlansMock: vi.fn(),
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

// 自适应计划现在总是与学习入口动作一起渲染，这里隔离它的网络请求。
vi.mock('@/api/adaptivePlans', () => ({
  listAdaptivePlans: (...args: unknown[]) => listAdaptivePlansMock(...args),
  getAdaptivePlan: vi.fn(),
  createAdaptivePlan: vi.fn(),
  updateAdaptiveTask: vi.fn(),
  proposeAdjustment: vi.fn(),
  applyAdjustment: vi.fn(),
  undoAdjustment: vi.fn(),
  addAdaptiveTask: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock, replace: vi.fn() }),
  useRoute: () => ({ query: routeQuery, path: '/learning-plan' }),
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
  listAdaptivePlansMock.mockReset()
  listAdaptivePlansMock.mockResolvedValue([])
  Object.assign(routeQuery, {
    courseId: 'ai_intro',
    nodeId: 'ml-basics',
    stepId: '7',
    actionKind: 'resume_plan',
    source: 'learning_snapshot',
  })
})

async function fillActionForm(wrapper: ReturnType<typeof mount>, minutes: number, level: string) {
  await wrapper.find('[data-test="action-minutes"]').setValue(minutes)
  await wrapper.find('[data-test="action-level"]').setValue(level)
}

describe('LearningPlanPage 学习入口真实动作', () => {
  it('承接 resume_plan 上下文，用真实用时与自评提交计划 progress 接口', async () => {
    getLearningSnapshotMock.mockResolvedValue(snapshot)
    updatePlanProgressMock.mockResolvedValue({ status: 'completed', message: '步骤已完成' })

    const wrapper = mount(LearningPlanPage)
    await flushPromises()

    expect(wrapper.text()).toContain('模型评估')
    expect(wrapper.find('[data-test="complete-learning-action"]').exists()).toBe(true)
    // 提交前必须由用户填写，不能默认满分
    expect(wrapper.find('[data-test="complete-learning-action"]').attributes('disabled')).toBeDefined()

    await fillActionForm(wrapper, 25, 'shaky')
    await wrapper.find('[data-test="complete-learning-action"]').trigger('click')
    await flushPromises()

    expect(updatePlanProgressMock).toHaveBeenCalledWith(42, {
      step_id: 7,
      step_order: 2,
      status: 'completed',
      activity_type: 'study',
      score: 0.6,
      duration_minutes: 25,
    })
    expect(routerPushMock).toHaveBeenCalledWith({
      path: '/learning-analysis',
      query: { courseId: 'ai_intro', progressStatus: '步骤已完成' },
    })
  })

  it('不再固定提交 score 1 / duration 0 这类无依据数据', async () => {
    getLearningSnapshotMock.mockResolvedValue(snapshot)
    updatePlanProgressMock.mockResolvedValue({ status: 'completed' })

    const wrapper = mount(LearningPlanPage)
    await flushPromises()
    await fillActionForm(wrapper, 40, 'solid')
    await wrapper.find('[data-test="complete-learning-action"]').trigger('click')
    await flushPromises()

    const payload = updatePlanProgressMock.mock.calls[0][1] as Record<string, number>
    expect(payload.score).not.toBe(1)
    expect(payload.duration_minutes).toBe(40)
  })

  it('review_current_node 使用 review 动作类型而不是只切换本地 checkbox', async () => {
    Object.assign(routeQuery, { actionKind: 'review_current_node', stepId: '' })
    getLearningSnapshotMock.mockResolvedValue(snapshot)
    updatePlanProgressMock.mockResolvedValue({ status: 'completed' })

    const wrapper = mount(LearningPlanPage)
    await flushPromises()
    await fillActionForm(wrapper, 12, 'stuck')
    await wrapper.find('[data-test="complete-learning-action"]').trigger('click')
    await flushPromises()

    expect(updatePlanProgressMock).toHaveBeenCalledWith(42, expect.objectContaining({
      step_id: 7,
      activity_type: 'review',
      score: 0.3,
      duration_minutes: 12,
    }))
  })

  it('带 actionKind 进入时自适应计划仍然可见，动作卡片说明它改的是快照计划', async () => {
    getLearningSnapshotMock.mockResolvedValue(snapshot)

    const wrapper = mount(LearningPlanPage)
    await flushPromises()

    expect(wrapper.find('.adaptive-workspace').exists()).toBe(true)
    expect(wrapper.find('.learning-action-context').text()).toContain('AI 工程师学习路径')
    expect(wrapper.find('.learning-action-context').text()).toContain('不会自动改动下面的自适应计划')
  })
})
