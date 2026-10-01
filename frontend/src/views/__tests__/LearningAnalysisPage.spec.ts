import { describe, expect, it, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LearningAnalysisPage from '../LearningAnalysisPage.vue'

const { getLearningSnapshotMock, routerPushMock, routeQuery } = vi.hoisted(() => ({
  getLearningSnapshotMock: vi.fn(),
  routerPushMock: vi.fn(),
  routeQuery: {} as Record<string, string>,
}))

vi.mock('@/api/learningSnapshot', () => ({
  getLearningSnapshot: (...args: unknown[]) => getLearningSnapshotMock(...args),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
  useRoute: () => ({ query: routeQuery }),
}))

const makeSnapshot = (overrides: Record<string, unknown> = {}) => ({
  student_id: 1,
  course_id: 'ai_intro',
  generated_at: '2026-09-28T10:00:00Z',
  active_plan: {
    plan_id: 42,
    title: 'AI 工程师学习路径',
    status: 'in_progress',
    interrupted: false,
    current_step: { step_id: 7, order: 2, topic: '模型评估', node_id: 'ml-basics', status: 'in_progress' },
  },
  current_node: { node_id: 'ml-basics', name: '模型评估', reason: 'current_step_node' },
  mastery: { node_id: 'ml-basics', value: 0.42, level: 'learning', source: 'node_masteries', last_evidence_at: null },
  recent_evidence: [],
  profile_context: null,
  freshness: { stale: false, missing_sources: [], computed_from: ['active_plan', 'mastery', 'graph'] },
  next_action: {
    action_kind: 'review_current_node',
    target: { node_id: 'ml-basics', step_id: 7 },
    reason: ['evidence-123'],
    expected_minutes: 15,
    entry: '/learning-path',
    dismiss_policy: 'snooze',
  },
  ...overrides,
})

const mountPage = () => mount(LearningAnalysisPage)

beforeEach(() => {
  getLearningSnapshotMock.mockReset()
  routerPushMock.mockReset()
  Object.keys(routeQuery).forEach((key) => delete routeQuery[key])
})

describe('LearningAnalysisPage 学习入口建议卡', () => {
  it('加载真实快照后只显示一张建议卡，并显示快照中的目标、理由和时长', async () => {
    getLearningSnapshotMock.mockResolvedValue(makeSnapshot())

    const wrapper = mountPage()
    await flushPromises()

    expect(getLearningSnapshotMock).toHaveBeenCalledWith('ai_intro')
    expect(wrapper.find('[data-test="next-action-card"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="next-action-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('复习当前知识点')
    expect(wrapper.text()).toContain('模型评估')
    expect(wrapper.text()).toContain('evidence-123')
    expect(wrapper.text()).toContain('预计 15 分钟')
    expect(wrapper.text()).not.toContain('矩阵运算专项练习')
  })

  it('没有 next_action 时显示诚实空状态和手动入口，不显示旧静态推荐', async () => {
    getLearningSnapshotMock.mockResolvedValue(makeSnapshot({ next_action: null }))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('暂时没有一条明确的下一步')
    expect(wrapper.text()).toContain('手动选择学习入口')
    expect(wrapper.text()).not.toContain('矩阵运算专项练习')
    expect(wrapper.text()).not.toContain('Transformer 案例学习')
  })

  it('快照请求失败时显示可重试错误，不回退到静态推荐', async () => {
    getLearningSnapshotMock.mockRejectedValue(new Error('快照接口不可用'))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('暂时无法生成可靠的下一步建议')
    expect(wrapper.text()).toContain('快照接口不可用')
    expect(wrapper.find('[data-test="refresh-snapshot"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Transformer 案例学习')
    expect(wrapper.find('.analysis-page').classes()).toContain('snapshot-unavailable')
    expect(wrapper.find('.summary-grid').exists()).toBe(false)
  })

  it('点击开始只按 next_action.entry 导航一次，并传递 action 上下文', async () => {
    getLearningSnapshotMock.mockResolvedValue(makeSnapshot())

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('[data-test="start-next-action"]').trigger('click')

    expect(routerPushMock).toHaveBeenCalledTimes(1)
    expect(routerPushMock).toHaveBeenCalledWith({
      path: '/learning-path',
      query: {
        courseId: 'ai_intro',
        nodeId: 'ml-basics',
        stepId: '7',
        actionKind: 'review_current_node',
        source: 'learning_snapshot',
      },
    })
  })

  it('freshness 不完整时隐藏建议卡并提示数据状态', async () => {
    getLearningSnapshotMock.mockResolvedValue(makeSnapshot({
      freshness: { stale: true, missing_sources: ['mastery'], computed_from: ['active_plan'] },
    }))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('学习数据不完整')
    expect(wrapper.find('[data-test="next-action-card"]').exists()).toBe(false)
  })

  it('快照缺少 freshness 时也不展示建议卡', async () => {
    getLearningSnapshotMock.mockResolvedValue(makeSnapshot({ freshness: undefined }))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('学习数据不完整')
    expect(wrapper.find('[data-test="next-action-card"]').exists()).toBe(false)
  })
})
