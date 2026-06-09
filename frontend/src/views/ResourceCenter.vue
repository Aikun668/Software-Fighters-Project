<template>
  <div class="resource-center">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>资源中心</h1>
      <p>探索丰富的AI学习资源</p>
    </div>

    <!-- 顶部操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="showGenerateDialog = true">
        <el-icon icon="Plus" />
        生成新资源
      </el-button>
      <div class="filter-tabs">
        <el-tabs v-model="activeFilter" @tab-change="handleFilterChange">
          <el-tab-pane label="全部" name="all"></el-tab-pane>
          <el-tab-pane label="课程文档" name="document"></el-tab-pane>
          <el-tab-pane label="思维导图" name="mindmap"></el-tab-pane>
          <el-tab-pane label="练习题" name="exercise"></el-tab-pane>
          <el-tab-pane label="拓展阅读" name="reading"></el-tab-pane>
          <el-tab-pane label="代码案例" name="code"></el-tab-pane>
          <el-tab-pane label="记忆闪卡" name="flashcards"></el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 资源卡片网格 -->
    <div class="resource-grid">
      <div
        v-for="resource in filteredResources"
        :key="resource.id"
        class="resource-card"
      >
        <div class="card-icon" :class="getResourceIconClass(resource.type)">
          <el-icon :icon="getIcon(resource.type)" />
        </div>
        <div class="card-content">
          <h3 class="card-title">{{ resource.title }}</h3>
          <p class="card-description">{{ resource.description }}</p>
          <div class="card-meta">
            <el-tag size="small" :type="getTagType(resource.type)">
              {{ getTypeLabel(resource.type) }}
            </el-tag>
            <span class="create-time">{{ resource.createdAt }}</span>
          </div>
        </div>
        <div class="card-actions">
          <el-button size="small" @click="viewResource(resource)">
            <el-icon icon="Eye" />
            查看
          </el-button>
          <el-button size="small" @click="editResource(resource)">
            <el-icon icon="Edit" />
            编辑
          </el-button>
        </div>
      </div>
    </div>

    <!-- 生成资源对话框 -->
    <el-dialog
      title="生成新资源"
      :visible="showGenerateDialog"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="generate-form">
        <el-form :model="generateForm" label-width="100px">
          <el-form-item label="资源类型">
            <el-select v-model="generateForm.type" placeholder="请选择资源类型">
              <el-option label="课程文档" value="document"></el-option>
              <el-option label="思维导图" value="mindmap"></el-option>
              <el-option label="练习题" value="exercise"></el-option>
              <el-option label="拓展阅读" value="reading"></el-option>
              <el-option label="代码案例" value="code"></el-option>
              <el-option label="记忆闪卡" value="flashcards"></el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="知识点">
            <el-input
              v-model="generateForm.topic"
              placeholder="输入要生成的知识点"
            ></el-input>
          </el-form-item>
          <el-form-item label="详细描述">
            <el-input
              type="textarea"
              v-model="generateForm.description"
              :rows="3"
              placeholder="对生成内容的要求（可选）"
            ></el-input>
          </el-form-item>
        </el-form>

        <!-- 生成进度 -->
        <div v-if="isGenerating" class="generate-progress">
          <div class="progress-header">
            <span>正在生成资源...</span>
            <span class="progress-percent">{{ generateProgress }}%</span>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: generateProgress + '%' }"
            ></div>
          </div>
          <p class="progress-tips">{{ progressTips }}</p>
        </div>
      </div>

      <template #footer>
        <el-button @click="showGenerateDialog = false" :disabled="isGenerating">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="generateResource"
          :disabled="!generateForm.type || !generateForm.topic || isGenerating"
        >
          {{ isGenerating ? '生成中...' : '生成' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

interface Resource {
  id: string
  type: 'document' | 'mindmap' | 'exercise' | 'reading' | 'code' | 'flashcards'
  title: string
  description: string
  createdAt: string
}

const activeFilter = ref('all')
const showGenerateDialog = ref(false)
const isGenerating = ref(false)
const generateProgress = ref(0)
const progressTips = ref('')

const generateForm = ref<{ type: string; topic: string; description: string }>({
  type: '',
  topic: '',
  description: ''
})

const resources = ref<Resource[]>([
  { id: '1', type: 'document', title: '深度学习入门指南', description: '从零开始学习深度学习的基础知识，包括神经网络、反向传播等核心概念', createdAt: '2024-01-15' },
  { id: '2', type: 'mindmap', title: '机器学习算法体系', description: '全面梳理机器学习算法的分类、应用场景和优缺点', createdAt: '2024-01-14' },
  { id: '3', type: 'exercise', title: '线性回归实战练习', description: '通过实际数据集练习线性回归模型的实现和调优', createdAt: '2024-01-13' },
  { id: '4', type: 'reading', title: 'Attention Is All You Need', description: 'Transformer架构的经典论文精读与解读', createdAt: '2024-01-12' },
  { id: '5', type: 'code', title: 'CNN图像分类实现', description: '使用PyTorch实现卷积神经网络进行图像分类', createdAt: '2024-01-11' },
  { id: '6', type: 'document', title: 'PyTorch基础教程', description: 'PyTorch框架的入门教程，涵盖张量操作、自动微分等', createdAt: '2024-01-10' },
  { id: '7', type: 'mindmap', title: 'NLP技术图谱', description: '自然语言处理领域的技术体系和发展脉络', createdAt: '2024-01-09' },
  { id: '8', type: 'exercise', title: '逻辑回归分类练习', description: '练习使用逻辑回归解决分类问题', createdAt: '2024-01-08' },
  { id: '9', type: 'reading', title: 'BERT论文解读', description: 'BERT模型的原理、架构和应用场景详解', createdAt: '2024-01-07' },
  { id: '10', type: 'code', title: 'RNN文本生成', description: '使用循环神经网络生成文本的完整实现', createdAt: '2024-01-06' },
  { id: '11', type: 'document', title: '强化学习入门', description: '强化学习的基本概念、算法和应用案例', createdAt: '2024-01-05' },
  { id: '12', type: 'mindmap', title: '深度学习优化策略', description: '优化器选择、学习率调度、正则化等技巧', createdAt: '2024-01-04' },
  { id: '13', type: 'flashcards', title: '神经网络基础闪卡', description: '包含神经网络基本概念、激活函数、损失函数等核心知识点的记忆闪卡', createdAt: '2024-01-03' },
  { id: '14', type: 'flashcards', title: 'PyTorch API闪卡', description: '常用PyTorch函数和类的速记卡片', createdAt: '2024-01-02' }
])

const filteredResources = computed(() => {
  if (activeFilter.value === 'all') {
    return resources.value
  }
  return resources.value.filter(r => r.type === activeFilter.value)
})

const getResourceIconClass = (type: string) => {
  const classes: Record<string, string> = {
    document: 'doc-icon',
    mindmap: 'mind-icon',
    exercise: 'exer-icon',
    reading: 'read-icon',
    code: 'code-icon',
    flashcards: 'flash-icon'
  }
  return classes[type] || 'doc-icon'
}

const getIcon = (type: string) => {
  const icons: Record<string, string> = {
    document: 'FileText',
    mindmap: 'GitBranch',
    exercise: 'HelpCircle',
    reading: 'Bookmark',
    code: 'Code',
    flashcards: 'Layers'
  }
  return icons[type] || 'FileText'
}

const getTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    document: '课程文档',
    mindmap: '思维导图',
    exercise: '练习题',
    reading: '拓展阅读',
    code: '代码案例',
    flashcards: '记忆闪卡'
  }
  return labels[type] || '未知'
}

const getTagType = (type: string) => {
  const types: Record<string, string> = {
    document: 'primary',
    mindmap: 'success',
    exercise: 'warning',
    reading: 'info',
    code: 'danger',
    flashcards: 'primary'
  }
  return types[type] || 'default'
}

const handleFilterChange = () => {
}

const viewResource = (resource: Resource) => {
  console.log('查看资源:', resource)
}

const editResource = (resource: Resource) => {
  console.log('编辑资源:', resource)
}

const generateResource = async () => {
  isGenerating.value = true
  generateProgress.value = 0
  
  const tips: string[] = [
    '正在分析知识点...',
    '正在检索相关资料...',
    '正在生成内容...',
    '正在优化格式...',
    '生成完成！'
  ]
  
  for (let i = 0; i <= 100; i += 5) {
    if (!isGenerating.value) break
    generateProgress.value = i
    const tipIndex = Math.min(Math.floor(i / 25), tips.length - 1)
    progressTips.value = tips[tipIndex] ?? ''
    await new Promise(resolve => setTimeout(resolve, 150))
  }
  
  isGenerating.value = false
  showGenerateDialog.value = false
  
  resources.value.unshift({
    id: Date.now().toString(),
    type: generateForm.value.type as 'document' | 'mindmap' | 'exercise' | 'reading' | 'code' | 'flashcards',
    title: generateForm.value.topic || '未命名资源',
    description: generateForm.value.description || '根据您的需求生成的学习资源',
    createdAt: new Date().toISOString().split('T')[0]
  })
  
  generateForm.value = { type: '', topic: '', description: '' }
  
  ElMessage.success('资源生成成功！')
}
</script>

<style scoped>
.resource-center {
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

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.filter-tabs {
  flex: 1;
  margin-left: 24px;
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.resource-card {
  background-color: var(--card-bg);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-md);
  transition: all 0.3s ease;
}

.resource-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.card-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-bottom: 16px;
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

.flash-icon {
  background-color: rgba(126, 94, 246, 0.1);
  color: #7E5CF6;
}

.card-content {
  flex: 1;
}

.card-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.card-description {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.create-time {
  font-size: 12px;
  color: #909399;
}

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f2f6fc;
}

.generate-form {
  padding: 16px 0;
}

.generate-progress {
  margin-top: 20px;
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.progress-percent {
  font-weight: 600;
  color: #409eff;
}

.progress-bar {
  height: 8px;
  background-color: #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #409eff, #67c23a);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-tips {
  margin: 8px 0 0 0;
  font-size: 13px;
  color: #606266;
}
</style>
