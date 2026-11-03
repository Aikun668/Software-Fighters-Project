import api from '@/utils/request'

export type LearningActionKind =
  | 'resume_plan'
  | 'review_current_node'
  | 'practice_targeted_questions'
  | 'check_prerequisite'
  | 'study_assigned_resource'
  | 'ask_for_explanation'

export type LearningDismissPolicy = 'snooze' | 'alternative' | 'manual_pick'

export interface LearningSnapshotTarget {
  node_id?: string | null
  step_id?: number | null
  resource_topic?: string | null
}

export interface LearningNextAction {
  action_kind: LearningActionKind
  target: LearningSnapshotTarget
  reason: string[]
  expected_minutes?: number | null
  entry: string
  dismiss_policy: LearningDismissPolicy
}

export interface LearningPlanStepSnapshot {
  step_id: number
  order: number
  topic: string
  node_id: string | null
  status: string
}

export interface LearningActivePlanSnapshot {
  plan_id: number | null
  title: string
  status: string
  current_step: LearningPlanStepSnapshot | null
  interrupted: boolean
}

export interface LearningCurrentNodeSnapshot {
  node_id: string
  name: string
  reason: string
}

export interface LearningMasterySnapshot {
  node_id: string | null
  value: number | null
  level: string
  source: string
  last_evidence_at?: string | null
}

export interface LearningFreshnessSnapshot {
  stale: boolean
  missing_sources: string[]
  computed_from: string[]
}

export interface LearningSnapshot {
  student_id: number
  course_id: string
  generated_at: string
  active_plan: LearningActivePlanSnapshot | null
  current_node: LearningCurrentNodeSnapshot | null
  mastery: LearningMasterySnapshot
  recent_evidence: Array<Record<string, unknown>>
  profile_context?: Record<string, unknown> | null
  freshness: LearningFreshnessSnapshot
  next_action?: LearningNextAction | null
}

interface LearningSnapshotEnvelope {
  success?: boolean
  data?: LearningSnapshot | null
}

const isLearningSnapshot = (value: unknown): value is LearningSnapshot => {
  if (!value || typeof value !== 'object') return false

  const candidate = value as Record<string, unknown>
  return typeof candidate.student_id === 'number' && typeof candidate.course_id === 'string'
}

/**
 * Java 外层结果已由 request 工具拆掉；这里再拆掉 Python 桥接保留的
 * { success, data: 学习快照 } 外壳，页面始终只拿到真正的学习快照。
 */
const unwrapLearningSnapshot = (
  response: LearningSnapshot | LearningSnapshotEnvelope,
): LearningSnapshot => {
  if (isLearningSnapshot(response)) return response

  if (
    response &&
    typeof response === 'object' &&
    'data' in response &&
    isLearningSnapshot(response.data)
  ) {
    return response.data
  }

  throw new Error('学习快照接口返回格式不正确')
}

/** 读取 Java 桥接的只读学习快照；前端不拼装学习状态，也不访问 Python 内部接口。 */
export const getLearningSnapshot = (courseId: string): Promise<LearningSnapshot> => {
  return api
    .get<LearningSnapshot | LearningSnapshotEnvelope>('/learning-snapshot', { courseId })
    .then(unwrapLearningSnapshot)
}
