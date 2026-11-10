<template>
  <div class="learning-path">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>学习路径</h1>
      <p>按照规划的路径，一步步掌握AI知识</p>
    </div>

    <!-- 路径概览卡片 -->
    <div class="path-overview">
      <div class="overview-card">
        <div class="overview-header">
          <div class="path-info">
            <h2>{{ currentPath.name }}</h2>
            <p>{{ currentPath.description }}</p>
          </div>
          <div class="path-badge">{{ currentPath.duration }}</div>
        </div>
        <div class="progress-summary">
          <div class="progress-text">
            <span>学习进度</span>
            <span class="progress-value">{{ overallProgress }}%</span>
          </div>
          <div class="progress-bar-large">
            <div
              class="progress-fill-large"
              :style="{ width: overallProgress + '%' }"
            ></div>
          </div>
          <div class="progress-stats">
            <span>已完成 {{ completedModules }} / {{ totalModules }} 个模块</span>
            <span>剩余 {{ remainingHours }} 小时</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 学习路径时间线 -->
    <div class="timeline-container">
      <div class="timeline">
        <div
          v-for="(module, index) in modules"
          :key="module.id"
          class="timeline-item"
        >
          <!-- 时间线节点 -->
          <div class="timeline-node">
            <div class="node-circle" :class="module.status">
              <el-icon v-if="module.status === 'completed'" icon="Check" />
              <el-icon v-else-if="module.status === 'current'" icon="Play" />
              <span v-else>{{ index + 1 }}</span>
            </div>
            <div v-if="index < modules.length - 1" class="node-line" :class="getLineClass(index)"></div>
          </div>

          <!-- 模块卡片 -->
          <div class="module-card" :class="module.status">
            <div class="card-header">
              <div class="module-info">
                <h3 class="module-title">{{ module.title }}</h3>
                <p class="module-desc">{{ module.description }}</p>
              </div>
              <el-tag :type="getStatusTagType(module.status)" size="small">
                {{ getStatusLabel(module.status) }}
              </el-tag>
            </div>

            <!-- 模块资源列表 -->
            <div class="resource-list">
              <div
                v-for="resource in module.resources"
                :key="resource.id"
                class="resource-item"
                @click="navigateToResource(resource)"
              >
                <div class="resource-icon" :class="getResourceIcon(resource.type)">
                  <el-icon :icon="getIcon(resource.type)" />
                </div>
                <div class="resource-info">
                  <span class="resource-name">{{ resource.name }}</span>
                  <span class="resource-type">{{ getResourceTypeLabel(resource.type) }}</span>
                </div>
                <el-icon class="arrow-icon" icon="ChevronRight" />
              </div>
            </div>

            <!-- 模块进度 -->
            <div class="module-progress">
              <div class="progress-info">
                <span>模块进度</span>
                <span>{{ module.progress }}%</span>
              </div>
              <div class="mini-progress-bar">
                <div
                  class="mini-progress-fill"
                  :style="{ width: module.progress + '%' }"
                ></div>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="card-actions">
              <el-button
                v-if="module.status === 'current' || module.status === 'pending'"
                type="primary"
                size="small"
                @click="startModule(module)"
              >
                <el-icon icon="Play" />
                {{ module.status === 'current' ? '继续学习' : '开始学习' }}
              </el-button>
              <el-button
                v-if="module.status === 'completed'"
                size="small"
                @click="reviewModule(module)"
              >
                <el-icon icon="Refresh" />
                复习
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 学习建议 -->
    <div class="suggestions">
      <div class="card">
        <h3 class="card-title">学习建议</h3>
        <div class="suggestion-list">
          <div
            v-for="(suggestion, index) in suggestions"
            :key="index"
            class="suggestion-item"
          >
            <el-icon class="suggestion-icon" icon="Lightbulb" />
            <p>{{ suggestion }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Resource {
  id: string
  name: string
  type: 'document' | 'mindmap' | 'exercise' | 'reading' | 'code'
}

interface Module {
  id: string
  title: string
  description: string
  status: 'completed' | 'current' | 'pending'
  progress: number
  resources: Resource[]
}

const currentPath = ref({
  name: 'AI入门学习路径',
  description: '从零基础到掌握AI核心技能的完整学习路径',
  duration: '12周'
})

const modules = ref<Module[]>([
  {
    id: '1',
    title: 'Python基础',
    description: '掌握Python编程语言的基本语法和常用库',
    status: 'completed',
    progress: 100,
    resources: [
      { id: 'r1', name: 'Python基础教程', type: 'document' },
      { id: 'r2', name: 'Python语法思维导图', type: 'mindmap' },
      { id: 'r3', name: 'Python练习题', type: 'exercise' }
    ]
  },
  {
    id: '2',
    title: '数学基础',
    description: '复习线性代数、微积分和概率统计知识',
    status: 'completed',
    progress: 100,
    resources: [
      { id: 'r4', name: '线性代数回顾', type: 'document' },
      { id: 'r5', name: '概率统计基础', type: 'document' },
      { id: 'r6', name: '数学练习题', type: 'exercise' }
    ]
  },
  {
    id: '3',
    title: '机器学习入门',
    description: '学习机器学习的基本概念和经典算法',
    status: 'current',
    progress: 60,
    resources: [
      { id: 'r7', name: '机器学习导论', type: 'document' },
      { id: 'r8', name: '监督学习算法', type: 'document' },
      { id: 'r9', name: '算法思维导图', type: 'mindmap' },
      { id: 'r10', name: '机器学习实战', type: 'code' }
    ]
  },
  {
    id: '4',
    title: '深度学习基础',
    description: '深入学习神经网络和深度学习框架',
    status: 'pending',
    progress: 0,
    resources: [
      { id: 'r11', name: '神经网络原理', type: 'document' },
      { id: 'r12', name: 'PyTorch框架', type: 'document' },
      { id: 'r13', name: 'CNN详解', type: 'reading' },
      { id: 'r14', name: '深度学习练习', type: 'code' }
    ]
  },
  {
    id: '5',
    title: '自然语言处理',
    description: '学习NLP的核心技术和应用',
    status: 'pending',
    progress: 0,
    resources: [
      { id: 'r15', name: 'NLP基础', type: 'document' },
      { id: 'r16', name: 'Transformer架构', type: 'reading' },
      { id: 'r17', name: 'BERT实战', type: 'code' }
    ]
  },
  {
    id: '6',
    title: '项目实战',
    description: '完成综合AI项目，巩固所学知识',
    status: 'pending',
    progress: 0,
    resources: [
      { id: 'r18', name: '项目案例分析', type: 'document' },
      { id: 'r19', name: '实战项目代码', type: 'code' },
      { id: 'r20', name: '项目答辩准备', type: 'reading' }
    ]
  }
])

const suggestions = ref([
  '建议每天学习1-2小时，保持学习节奏',
  '完成每个模块后进行复习和总结',
  '多做练习题巩固所学知识',
  '参与社区讨论，与其他学习者交流'
])

const totalModules = computed(() => modules.value.length)
const completedModules = computed(() => modules.value.filter(m => m.status === 'completed').length)
const overallProgress = computed(() => {
  const total = modules.value.reduce((sum, m) => sum + m.progress, 0)
  return Math.round(total / totalModules.value)
})
const remainingHours = computed(() => {
  const pendingModules = modules.value.filter(m => m.status === 'pending').length
  return pendingModules * 8
})

const getLineClass = (index: number) => {
  const currentModule = modules.value[index]
  const nextModule = modules.value[index + 1]
  if (currentModule.status === 'completed' && nextModule.status === 'completed') {
    return 'completed'
  }
  if (currentModule.status === 'completed' && (nextModule.status === 'current' || nextModule.status === 'pending')) {
    return 'active'
  }
  return 'pending'
}

const getStatusTagType = (status: string) => {
  const types: Record<string, string> = {
    completed: 'success',
    current: 'primary',
    pending: 'info'
  }
  return types[status] || 'default'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    completed: '已完成',
    current: '进行中',
    pending: '待学习'
  }
  return labels[status] || '未知'
}

const getResourceIcon = (type: string) => {
  const icons: Record<string, string> = {
    document: 'doc-icon',
    mindmap: 'mind-icon',
    exercise: 'exer-icon',
    reading: 'read-icon',
    code: 'code-icon'
  }
  return icons[type] || 'doc-icon'
}

const getIcon = (type: string) => {
  const icons: Record<string, string> = {
    document: 'FileText',
    mindmap: 'GitBranch',
    exercise: 'HelpCircle',
    reading: 'Bookmark',
    code: 'Code'
  }
  return icons[type] || 'FileText'
}

const getResourceTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    document: '课程文档',
    mindmap: '思维导图',
    exercise: '练习题',
    reading: '拓展阅读',
    code: '代码案例'
  }
  return labels[type] || '未知'
}

const navigateToResource = (resource: Resource) => {
  console.log('导航到资源:', resource)
}

const startModule = (module: Module) => {
  console.log('开始学习模块:', module.title)
}

const reviewModule = (module: Module) => {
  console.log('复习模块:', module.title)
}
</script>

<style scoped>
.learning-path {
  padding: 24px;
  background-color: var(--bg-color);
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--primary-color);
}

.page-header p {
  margin: 0;
  color: var(--text-light);
}

.path-overview {
  margin-bottom: 32px;
}

.overview-card {
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--success-color) 100%);
  border-radius: 16px;
  padding: 28px;
  color: white;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.path-info h2 {
  margin: 0 0 8px 0;
  font-size: 20px;
}

.path-info p {
  margin: 0;
  opacity: 0.9;
}

.path-badge {
  background-color: rgba(255, 255, 255, 0.2);
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 14px;
}

.progress-summary {
  background-color: rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  padding: 20px;
}

.progress-text {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.progress-value {
  font-size: 24px;
  font-weight: 600;
}

.progress-bar-large {
  height: 8px;
  background-color: rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
}

.progress-fill-large {
  height: 100%;
  background-color: white;
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  opacity: 0.9;
}

.timeline-container {
  max-width: 800px;
  margin: 0 auto;
}

.timeline {
  position: relative;
}

.timeline-item {
  display: flex;
  margin-bottom: 24px;
}

.timeline-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 48px;
  flex-shrink: 0;
}

.node-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  z-index: 1;
}

.node-circle.completed {
  background-color: var(--success-color);
  color: white;
}

.node-circle.current {
  background-color: var(--primary-color);
  color: white;
}

.node-circle.pending {
  background-color: var(--border-light);
  color: var(--text-light);
}

.node-line {
  width: 3px;
  flex: 1;
  margin-top: 8px;
  min-height: 60px;
}

.node-line.completed {
  background-color: var(--success-color);
}

.node-line.active {
  background-color: var(--primary-color);
}

.node-line.pending {
  background-color: var(--border-light);
}

.module-card {
  flex: 1;
  background-color: var(--card-bg);
  border-radius: 12px;
  padding: 20px;
  margin-left: 16px;
  box-shadow: var(--shadow-md);
  border-left: 4px solid transparent;
}

.module-card.completed {
  border-left-color: var(--success-color);
}

.module-card.current {
  border-left-color: var(--primary-color);
}

.module-card.pending {
  border-left-color: var(--border-light);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.module-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
}

.module-desc {
  margin: 0;
  font-size: 13px;
  color: #606266;
}

.resource-list {
  margin-bottom: 16px;
}

.resource-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.resource-item:hover {
  background-color: var(--bg-light);
}

.resource-item:last-child {
  margin-bottom: 0;
}

.resource-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  margin-right: 12px;
}

.doc-icon {
  background-color: rgba(18, 46, 138, 0.1);
  color: var(--primary-color);
}

.mind-icon {
  background-color: rgba(103, 194, 58, 0.1);
  color: var(--success-color);
}

.exer-icon {
  background-color: rgba(230, 162, 60, 0.1);
  color: var(--warning-color);
}

.read-icon {
  background-color: rgba(144, 147, 153, 0.1);
  color: var(--text-secondary);
}

.code-icon {
  background-color: rgba(245, 108, 108, 0.1);
  color: var(--error-color);
}

.resource-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.resource-name {
  font-size: 14px;
  color: var(--text-primary);
}

.resource-type {
  font-size: 12px;
  color: var(--text-light);
}

.arrow-icon {
  color: #c0c4cc;
}

.module-progress {
  margin-bottom: 16px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 13px;
  color: #606266;
}

.mini-progress-bar {
  height: 6px;
  background-color: #e4e7ed;
  border-radius: 3px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #409eff, #67c23a);
  border-radius: 3px;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.suggestions {
  max-width: 800px;
  margin: 32px auto 0;
}

.card {
  background-color: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.08);
}

.card-title {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
}

.suggestion-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  padding: 12px;
  background-color: #fafafa;
  border-radius: 8px;
}

.suggestion-icon {
  color: #e6a23c;
  margin-right: 8px;
  font-size: 16px;
}

.suggestion-item p {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
</style>
