import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 学习资源接口定义
 * 支持5种资源类型：文档/思维导图/练习题/拓展阅读/代码案例
 */
export interface LearningResource {
  id: string                                          // 资源唯一标识
  type: 'document' | 'mindmap' | 'exercise' | 'reading' | 'code'  // 资源类型
  title: string                                       // 资源标题
  description: string                                 // 资源描述
  content: string                                     // 资源内容（markdown/html）
  progress: number                                    // 学习进度（0-100）
  completed: boolean                                  // 是否已完成
}

/**
 * 学习路径接口定义
 */
export interface LearningPath {
  id: string              // 路径唯一标识
  name: string            // 路径名称
  modules: LearningModule[] // 包含的模块列表
}

/**
 * 学习模块接口定义
 */
export interface LearningModule {
  id: string        // 模块唯一标识
  name: string      // 模块名称
  resources: string[] // 关联的资源ID列表
  completed: boolean // 是否已完成
  progress: number  // 模块进度（0-100）
}

// 全局状态定义
const resources = ref<LearningResource[]>([])     // 所有学习资源
const currentPath = ref<LearningPath | null>(null) // 当前学习路径
const currentResource = ref<LearningResource | null>(null) // 当前正在学习的资源
const learningProgress = ref(0)                   // 总体学习进度

/**
 * 学习资源管理Store
 * 负责管理5种学习资源和学习路径
 * 
 * @description
 * 核心功能：
 * - 管理课程文档、思维导图、练习题、拓展阅读、代码案例
 * - 维护学习路径和模块信息
 * - 追踪学习进度并自动计算总体进度
 * - 提供按类型筛选的资源列表
 */
export const useLearningStore = defineStore('learning', () => {
  /**
   * 设置学习资源列表
   * @param data - 资源数据数组
   */
  function setResources(data: LearningResource[]) {
    resources.value = data
  }

  /**
   * 设置当前学习资源
   * @param resource - 资源对象
   */
  function setCurrentResource(resource: LearningResource) {
    currentResource.value = resource
  }

  /**
   * 设置当前学习路径
   * @param path - 路径对象
   */
  function setCurrentPath(path: LearningPath) {
    currentPath.value = path
  }

  /**
   * 更新资源学习进度
   * @param resourceId - 资源ID
   * @param progress - 新进度值（0-100）
   */
  function updateProgress(resourceId: string, progress: number) {
    const resource = resources.value.find(r => r.id === resourceId)
    if (resource) {
      resource.progress = progress
      resource.completed = progress >= 100
      calculateOverallProgress()
    }
  }

  /**
   * 计算总体学习进度
   * 基于所有资源的平均进度计算
   */
  function calculateOverallProgress() {
    if (resources.value.length === 0) {
      learningProgress.value = 0
      return
    }
    const total = resources.value.reduce((sum, r) => sum + r.progress, 0)
    learningProgress.value = Math.round(total / resources.value.length)
  }

  // 计算属性：按类型筛选资源
  const documentResources = computed(() => resources.value.filter(r => r.type === 'document'))
  const mindmapResources = computed(() => resources.value.filter(r => r.type === 'mindmap'))
  const exerciseResources = computed(() => resources.value.filter(r => r.type === 'exercise'))
  const readingResources = computed(() => resources.value.filter(r => r.type === 'reading'))
  const codeResources = computed(() => resources.value.filter(r => r.type === 'code'))

  return {
    resources,
    currentPath,
    currentResource,
    learningProgress,
    documentResources,
    mindmapResources,
    exerciseResources,
    readingResources,
    codeResources,
    setResources,
    setCurrentResource,
    setCurrentPath,
    updateProgress
  }
})