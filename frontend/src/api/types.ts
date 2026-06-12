// API响应类型
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

// 分页响应
export interface PageResponse<T = any> {
  list: T[]
  total: number
}

// 用户模块类型
export interface UserRegisterRequest {
  username: string
  password: string
  passwordConfirm: string
  captchaKey: string
  captchaCode: string
}

export interface UserLoginRequest {
  username: string
  password: string
}

// 消息类型
export interface Message {
  id: number
  conversationId: number
  role: 'user' | 'assistant'
  content: string
  mode: string
  createdAt: string
}

// 会话类型
export interface Conversation {
  id: number
  userId: number
  title: string
  status: 'active' | 'archived'
  summary: string | null
  createdAt: string
  updatedAt: string
}

// 统一对话请求
export interface ChatRequest {
  message: string
  conversation_id: number | null
}

export interface ChatSSEEvent {
  delta: string
  mode: 'tutor' | 'path' | 'resource' | 'profile' | 'chat'
}

// 资源类型
export interface Resource {
  id: number
  userId: number
  type: 'course_doc' | 'mind_map' | 'exercise' | 'reading' | 'code_practice'
  topic: string
  title: string
  contentJson: string
  filePath: string | null
  createdAt: string
}

// 习题类型
export interface ExerciseRequest {
  topic: string
  count?: number
  difficulty?: 'easy' | 'medium' | 'hard'
}

export interface ExerciseGradeRequest {
  type: 'choice' | 'multi' | 'fill' | 'code' | 'essay'
  user_answer: string
  correct_answer?: string
  choices?: string[]
  multi?: boolean
  points?: number
  reference_answer?: string
  rubric?: string
  resource_id?: number
}

export interface ExerciseGradeResponse {
  correct: boolean
  score: number
  maxScore: number
  explanation: string
  hint: string
}

// 画像类型
export interface ProfileChatRequest {
  messages: { role: string; content: string }[]
}

export interface ProfileStatus {
  profile_completeness: number
  missing_fields: string[]
}

export interface UserProfile {
  id: number
  phone: string
  username: string
  avatar?: string
  knowledgeBase?: number
  cognitiveStyle?: string[]
  learningGoals?: string
  learningRhythm?: {
    dailyHours: number
    frequency: string
  }
  entries?: {
    weak_points: ProfileEntry[]
    interest_direction: ProfileEntry[]
  }
}

export interface ProfileEntry {
  text: string
  confidence: number
  status: 'active' | 'tentative' | 'stale'
}

// 知识图谱类型
export interface KnowledgeNode {
  id: string
  name: string
  description: string
  difficulty: number
  mastery: number
}

export interface KnowledgeEdge {
  source: string
  target: string
  relation: string
  rationale: string
}

export interface KnowledgeGraph {
  courseId: string
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
}

// 学习计划类型
export interface PlanStep {
  id?: number
  node_id: string
  topic: string
  order: number
  node_type: 'learn' | 'practice'
  status?: 'pending' | 'in_progress' | 'completed' | 'locked'
  depth?: number
}

export interface LearningPlan {
  id: number
  userId: number
  courseId: string
  title: string
  status: 'in_progress' | 'completed' | 'paused'
  steps: PlanStep[]
  createdAt: string
  updatedAt: string
}

// 学习记录类型
export interface LearningRecord {
  id: number
  userId: number
  resourceId: number
  progress: number
  score: number
  timeSpent: number
  createdAt: string
}

export interface RecordStats {
  totalScore: number
  averageScore: number
  totalRecords: number
}

// 学习活动类型
export interface LearningActivity {
  id?: number
  user_id: number
  plan_id: number
  step_id: number
  activity_type: 'exercise' | 'review' | 'study'
  duration_minutes: number
  score: number
  createdAt?: string
}

export interface ScoreTrendItem {
  date: string
  score: number
}

// 文件上传类型
export interface FileUploadResponse {
  fileId: number
  fileName: string
  originalName: string
}

// 节点掌握度类型
export interface NodeMastery {
  nodeId: string
  userId: number
  courseId: string
  mastery: number
  reviewCount: number
  updatedAt?: string
}
