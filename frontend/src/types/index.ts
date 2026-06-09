/**
 * 用户画像接口定义
 */
export interface UserProfile {
  id: string                    // 用户唯一标识
  name: string                  // 用户姓名
  avatar: string                // 头像URL
  email: string                 // 邮箱地址
  major: string                 // 专业
  grade: string                 // 年级
  learningGoals: string[]       // 学习目标列表
  interests: string[]           // 兴趣标签列表
}

/**
 * 课程接口定义
 */
export interface Course {
  id: string                    // 课程唯一标识
  title: string                 // 课程标题
  description: string           // 课程描述
  cover: string                 // 课程封面图
  category: string              // 课程分类
  difficulty: 'beginner' | 'intermediate' | 'advanced'  // 难度等级
  duration: number              // 课程时长（分钟）
  lessonsCount: number          // 章节数量
  studentsCount: number         // 学习人数
  rating: number                // 课程评分
  tags: string[]                // 课程标签
  createdAt: string             // 创建时间
  updatedAt: string             // 更新时间
}

/**
 * 章节接口定义
 */
export interface Chapter {
  id: string                    // 章节唯一标识
  courseId: string              // 所属课程ID
  title: string                 // 章节标题
  description: string           // 章节描述
  content: string               // 章节内容（HTML或Markdown）
  duration: number              // 章节时长（分钟）
  order: number                 // 章节顺序
  videoUrl?: string             // 视频链接
  resources?: string[]          // 资源链接列表
}

/**
 * 学习路径接口定义
 */
export interface LearningPath {
  id: string                    // 路径唯一标识
  title: string                 // 路径标题
  description: string           // 路径描述
  cover: string                 // 路径封面图
  courses: string[]             // 包含的课程ID列表
  duration: number              // 预计学习时长（小时）
  level: 'beginner' | 'intermediate' | 'advanced'  // 适合等级
  tags: string[]                // 路径标签
  createdAt: string             // 创建时间
}

/**
 * 学习进度接口定义
 */
export interface LearningProgress {
  userId: string                // 用户ID
  courseId: string              // 课程ID
  chapterId?: string            // 当前章节ID
  progress: number              // 学习进度（0-100）
  completedChapters: string[]   // 已完成章节ID列表
  lastAccessTime: string        // 最后访问时间
  totalTime: number             // 累计学习时长（分钟）
}

/**
 * 消息接口定义
 */
export interface Message {
  id: string                    // 消息唯一标识
  userId: string                // 用户ID
  content: string               // 消息内容
  type: 'user' | 'ai'           // 消息类型
  timestamp: string             // 发送时间
}

/**
 * 分页响应接口定义
 */
export interface PaginationResponse<T> {
  data: T[]                     // 数据列表
  page: number                  // 当前页码
  size: number                  // 每页数量
  total: number                 // 总记录数
  pages: number                 // 总页数
}

/**
 * 通用响应接口定义
 */
export interface ApiResponse<T = any> {
  code: number                  // 状态码
  message: string               // 提示消息
  data: T                       // 数据内容
  success: boolean              // 是否成功
}
