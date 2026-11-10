<template>
  <div class="network-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="18" cy="5" r="3"/>
            <circle cx="6" cy="12" r="3"/>
            <circle cx="18" cy="19" r="3"/>
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
          </svg>
          学习资源关系网络
        </h1>
        <p class="page-subtitle">探索知识点之间的关联，发现学习路径</p>
      </div>
      <div class="header-actions">
        <button class="action-btn" @click="refreshData" title="刷新数据">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button class="action-btn" @click="resetZoom" title="重置视图">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="11" y1="8" x2="11" y2="14"/>
            <line x1="8" y1="11" x2="14" y2="11"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="page-content">
      <!-- 图表容器 -->
      <div class="chart-container" ref="chartContainer">
        <div v-if="!chartInstance" class="chart-loading">
          <div class="loading-spinner"></div>
          <span>正在加载关系图...</span>
        </div>
      </div>

      <!-- 右侧详情面板 -->
      <aside :class="['detail-panel', { 'show': selectedNode }]">
        <div v-if="selectedNode" class="node-detail">
          <div class="detail-header">
            <div class="node-icon" :style="{ background: getCategoryColor(selectedNode.category) }">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <path v-if="selectedNode.category === 'course'" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path v-if="selectedNode.category === 'course'" d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                <path v-if="selectedNode.category === 'concept'" d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path v-if="selectedNode.category === 'concept'" d="M2 17l10 5 10-5"/>
                <path v-if="selectedNode.category === 'concept'" d="M2 12l10 5 10-5"/>
                <path v-if="selectedNode.category === 'skill'" d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                <path v-if="selectedNode.category === 'project'" d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <button class="close-btn" @click="selectedNode = null">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          
          <h2 class="node-name">{{ selectedNode.name }}</h2>
          <span class="node-category">{{ getCategoryName(selectedNode.category) }}</span>
          
          <div class="detail-section">
            <h3>描述</h3>
            <p>{{ selectedNode.description || '暂无描述信息' }}</p>
          </div>
          
          <div class="detail-section">
            <h3>关联资源</h3>
            <ul class="related-list">
              <li 
                v-for="rel in selectedNode.relations" 
                :key="rel.target"
                class="related-item"
                @click="handleRelatedClick(rel.target)"
              >
                <span class="rel-type">{{ rel.type }}</span>
                <span class="rel-name">{{ rel.name }}</span>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </li>
            </ul>
          </div>
          
          <div class="detail-section">
            <h3>相关度</h3>
            <div class="relevance-bar">
              <div class="relevance-fill" :style="{ width: (selectedNode.relevance || 0) + '%' }"></div>
            </div>
            <span class="relevance-text">{{ selectedNode.relevance || 0 }}%</span>
          </div>
        </div>
        
        <div v-else class="empty-detail">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="18" cy="5" r="3"/>
            <circle cx="6" cy="12" r="3"/>
            <circle cx="18" cy="19" r="3"/>
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
          </svg>
          <p>点击节点查看详情</p>
        </div>
      </aside>
    </div>

    <!-- 图例 -->
    <div class="legend">
      <div class="legend-item">
        <span class="legend-dot" style="background: #10b981;"></span>
        <span>课程</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot" style="background: #7c3aed;"></span>
        <span>概念</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot" style="background: #f59e0b;"></span>
        <span>技能</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot" style="background: #3b82f6;"></span>
        <span>项目</span>
      </div>
    </div>

    <!-- 统计信息 -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-value">{{ networkData.nodes.length }}</span>
        <span class="stat-label">资源节点</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ networkData.edges.length }}</span>
        <span class="stat-label">关联关系</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ categoryStats.length }}</span>
        <span class="stat-label">资源类型</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed, nextTick } from 'vue'
import * as echarts from 'echarts'

interface NodeRelation {
  target: string
  name: string
  type: string
}

interface NetworkNode {
  id: string
  name: string
  category: 'course' | 'concept' | 'skill' | 'project'
  description?: string
  relevance?: number
  relations?: NodeRelation[]
}

interface NetworkEdge {
  source: string
  target: string
  label?: string
  lineStyle?: {
    opacity?: number
    width?: number
    color?: string
  }
}

interface NetworkData {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
}

// 网络数据
const networkData = reactive<NetworkData>({
  nodes: [
    // 课程
    { id: 'ml-course', name: '机器学习基础', category: 'course', description: '介绍机器学习的基本概念、算法和应用', relevance: 95 },
    { id: 'dl-course', name: '深度学习导论', category: 'course', description: '神经网络基础与深度学习核心技术', relevance: 88 },
    { id: 'nlp-course', name: '自然语言处理', category: 'course', description: 'NLP基础、文本分类、序列模型等', relevance: 82 },
    { id: 'cv-course', name: '计算机视觉', category: 'course', description: '图像处理、目标检测、图像分割等', relevance: 75 },
    
    // 概念
    { id: 'supervised', name: '监督学习', category: 'concept', description: '从标记数据中学习的机器学习方法', relevance: 90 },
    { id: 'unsupervised', name: '无监督学习', category: 'concept', description: '从无标记数据中发现模式的学习方法', relevance: 85 },
    { id: 'neural-net', name: '神经网络', category: 'concept', description: '受人脑启发的计算模型，是深度学习的基础', relevance: 92 },
    { id: 'cnn', name: '卷积神经网络', category: 'concept', description: '主要用于处理图像的神经网络结构', relevance: 88 },
    { id: 'rnn', name: '循环神经网络', category: 'concept', description: '处理序列数据的神经网络结构', relevance: 80 },
    { id: 'transformer', name: 'Transformer', category: 'concept', description: '基于自注意力机制的模型架构', relevance: 78 },
    { id: 'backprop', name: '反向传播', category: 'concept', description: '神经网络训练的核心算法', relevance: 85 },
    
    // 技能
    { id: 'python', name: 'Python编程', category: 'skill', description: 'Python基础语法和数据处理能力', relevance: 95 },
    { id: 'data-analysis', name: '数据分析', category: 'skill', description: '使用Pandas、NumPy进行数据处理', relevance: 88 },
    { id: 'model-tuning', name: '模型调优', category: 'skill', description: '超参数优化和模型性能提升技巧', relevance: 75 },
    { id: 'deploy', name: '模型部署', category: 'skill', description: '将模型部署到生产环境的能力', relevance: 70 },
    
    // 项目
    { id: 'house-prediction', name: '房价预测', category: 'project', description: '使用回归算法预测房价的实战项目', relevance: 82 },
    { id: 'digit-recognition', name: '手写数字识别', category: 'project', description: '使用CNN实现MNIST数据集分类', relevance: 85 },
    { id: 'sentiment-analysis', name: '情感分析', category: 'project', description: '使用RNN/LSTM进行文本情感分类', relevance: 78 },
    { id: 'chatbot', name: '智能聊天机器人', category: 'project', description: '基于Transformer构建对话系统', relevance: 72 }
  ],
  edges: [
    // 课程关联
    { source: 'ml-course', target: 'dl-course', label: '进阶', lineStyle: { color: '#10b981' } },
    { source: 'ml-course', target: 'supervised', label: '包含', lineStyle: { color: '#10b981' } },
    { source: 'ml-course', target: 'unsupervised', label: '包含', lineStyle: { color: '#10b981' } },
    { source: 'dl-course', target: 'neural-net', label: '基于', lineStyle: { color: '#7c3aed' } },
    { source: 'dl-course', target: 'cnn', label: '包含', lineStyle: { color: '#7c3aed' } },
    { source: 'dl-course', target: 'rnn', label: '包含', lineStyle: { color: '#7c3aed' } },
    { source: 'nlp-course', target: 'transformer', label: '基于', lineStyle: { color: '#7c3aed' } },
    { source: 'nlp-course', target: 'rnn', label: '涉及', lineStyle: { color: '#7c3aed' } },
    { source: 'cv-course', target: 'cnn', label: '核心', lineStyle: { color: '#7c3aed' } },
    
    // 概念关联
    { source: 'supervised', target: 'backprop', label: '使用', lineStyle: { color: '#f59e0b' } },
    { source: 'unsupervised', target: 'backprop', label: '间接', lineStyle: { color: '#f59e0b', opacity: 0.5 } },
    { source: 'neural-net', target: 'backprop', label: '依赖', lineStyle: { color: '#f59e0b' } },
    { source: 'cnn', target: 'neural-net', label: '属于', lineStyle: { color: '#7c3aed' } },
    { source: 'rnn', target: 'neural-net', label: '属于', lineStyle: { color: '#7c3aed' } },
    { source: 'transformer', target: 'neural-net', label: '属于', lineStyle: { color: '#7c3aed' } },
    { source: 'transformer', target: 'rnn', label: '替代', lineStyle: { color: '#f59e0b', opacity: 0.6 } },
    
    // 技能关联
    { source: 'ml-course', target: 'python', label: '需要', lineStyle: { color: '#3b82f6' } },
    { source: 'ml-course', target: 'data-analysis', label: '需要', lineStyle: { color: '#3b82f6' } },
    { source: 'dl-course', target: 'model-tuning', label: '涉及', lineStyle: { color: '#3b82f6' } },
    { source: 'dl-course', target: 'deploy', label: '最终', lineStyle: { color: '#3b82f6' } },
    
    // 项目关联
    { source: 'house-prediction', target: 'ml-course', label: '实践', lineStyle: { color: '#10b981' } },
    { source: 'house-prediction', target: 'supervised', label: '应用', lineStyle: { color: '#f59e0b' } },
    { source: 'house-prediction', target: 'data-analysis', label: '需要', lineStyle: { color: '#3b82f6' } },
    { source: 'digit-recognition', target: 'dl-course', label: '实践', lineStyle: { color: '#10b981' } },
    { source: 'digit-recognition', target: 'cnn', label: '使用', lineStyle: { color: '#7c3aed' } },
    { source: 'sentiment-analysis', target: 'nlp-course', label: '实践', lineStyle: { color: '#10b981' } },
    { source: 'sentiment-analysis', target: 'rnn', label: '使用', lineStyle: { color: '#7c3aed' } },
    { source: 'chatbot', target: 'nlp-course', label: '实践', lineStyle: { color: '#10b981' } },
    { source: 'chatbot', target: 'transformer', label: '基于', lineStyle: { color: '#7c3aed' } }
  ]
})

// 选中的节点
const selectedNode = ref<NetworkNode | null>(null)

// 图表实例
const chartContainer = ref<HTMLElement | null>(null)
const chartInstance = ref<echarts.ECharts | null>(null)

// 类别统计
const categoryStats = computed(() => {
  const categories = ['course', 'concept', 'skill', 'project']
  return categories.filter(cat => networkData.nodes.some(n => n.category === cat))
})

// 获取类别颜色
const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    course: '#10b981',
    concept: '#7c3aed',
    skill: '#f59e0b',
    project: '#3b82f6'
  }
  return colors[category] || '#6b7280'
}

// 获取类别名称
const getCategoryName = (category: string) => {
  const names: Record<string, string> = {
    course: '课程',
    concept: '概念',
    skill: '技能',
    project: '项目'
  }
  return names[category] || '未知'
}

// 初始化图表
const initChart = () => {
  if (!chartContainer.value) return

  chartInstance.value = echarts.init(chartContainer.value)

  const option = getChartOption()
  chartInstance.value.setOption(option)

  // 点击节点事件
  chartInstance.value.on('click', (params: any) => {
    if (params.dataType === 'node') {
      handleNodeClick(params.data as NetworkNode)
    }
  })

  // 窗口大小变化时自适应
  window.addEventListener('resize', handleResize)
}

// 获取图表配置
const getChartOption = () => {
  // 构建节点数据
  const nodes = networkData.nodes.map(node => ({
    id: node.id,
    name: node.name,
    category: node.category,
    draggable: true,
    itemStyle: {
      color: getCategoryColor(node.category)
    },
    label: {
      show: true,
      position: 'bottom',
      distance: 6,
      fontSize: 12,
      color: '#e5e7eb',
      formatter: node.name.length > 8 ? node.name.substring(0, 8) + '...' : node.name
    }
  }))

  // 构建边数据
  const edges = networkData.edges.map(edge => ({
    source: edge.source,
    target: edge.target,
    label: {
      show: !!edge.label,
      formatter: edge.label || '',
      fontSize: 10,
      color: '#9ca3af'
    },
    lineStyle: {
      color: edge.lineStyle?.color || '#6b7280',
      opacity: edge.lineStyle?.opacity || 0.6,
      width: edge.lineStyle?.width || 1.5,
      curveness: 0.2
    }
  }))

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17, 24, 39, 0.95)',
      borderColor: 'rgba(255, 255, 255, 0.1)',
      textStyle: {
        color: '#e5e7eb'
      },
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `<div style="font-weight: 600; margin-bottom: 4px;">${params.data.name}</div>
                  <div style="color: #9ca3af; font-size: 12px;">${getCategoryName(params.data.category)}</div>`
        }
        return ''
      }
    },
    legend: {
      show: false
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        symbolSize: 45,
        roam: true,
        draggable: true,
        focusNodeAdjacency: true,
        edgeSymbol: ['circle', 'arrow'],
        edgeSymbolSize: [6, 10],
        categories: [
          { name: 'course', itemStyle: { color: '#10b981' } },
          { name: 'concept', itemStyle: { color: '#7c3aed' } },
          { name: 'skill', itemStyle: { color: '#f59e0b' } },
          { name: 'project', itemStyle: { color: '#3b82f6' } }
        ],
        nodes: nodes,
        edges: edges,
        lineStyle: {
          opacity: 0.6,
          width: 1.5,
          curveness: 0.2
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3,
            opacity: 1
          },
          itemStyle: {
            borderWidth: 3,
            borderColor: '#ffffff'
          }
        },
        force: {
          repulsion: 1500,
          gravity: 0.1,
          edgeLength: [80, 200],
          layoutAnimation: true
        },
        animation: true,
        animationDuration: 1000,
        animationEasing: 'cubicOut'
      }
    ]
  }
}

// 处理节点点击
const handleNodeClick = (node: NetworkNode) => {
  // 查找该节点的关联信息
  const relations: NodeRelation[] = []
  
  networkData.edges.forEach(edge => {
    if (edge.source === node.id) {
      const targetNode = networkData.nodes.find(n => n.id === edge.target)
      if (targetNode) {
        relations.push({
          target: edge.target,
          name: targetNode.name,
          type: edge.label || '关联'
        })
      }
    }
    if (edge.target === node.id) {
      const sourceNode = networkData.nodes.find(n => n.id === edge.source)
      if (sourceNode) {
        relations.push({
          target: edge.source,
          name: sourceNode.name,
          type: edge.label || '关联'
        })
      }
    }
  })

  selectedNode.value = {
    ...node,
    relations
  }
}

// 处理关联节点点击
const handleRelatedClick = (nodeId: string) => {
  const node = networkData.nodes.find(n => n.id === nodeId)
  if (node) {
    handleNodeClick(node)
  }
}

// 刷新数据
const refreshData = () => {
  if (chartInstance.value) {
    const option = getChartOption()
    chartInstance.value.setOption(option, true)
  }
  selectedNode.value = null
}

// 重置缩放
const resetZoom = () => {
  if (chartInstance.value) {
    chartInstance.value.dispatchAction({
      type: 'graphRoam',
      zoom: 1,
      center: ['50%', '50%']
    })
  }
}

// 处理窗口大小变化
const handleResize = () => {
  if (chartInstance.value) {
    chartInstance.value.resize()
  }
}

// 生命周期
onMounted(() => {
  nextTick(() => {
    initChart()
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
})
</script>

<style scoped>
.network-page {
  height: calc(100vh - var(--header-height, 64px) - 48px);
  display: flex;
  flex-direction: column;
  background: var(--bg-page);
  border-radius: 16px;
  overflow: hidden;
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.page-title svg {
  color: var(--primary-color);
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

/* 主内容区 */
.page-content {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

/* 图表容器 */
.chart-container {
  flex: 1;
  height: 100%;
  min-height: 400px;
}

.chart-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  gap: 12px;
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 详情面板 */
.detail-panel {
  width: 320px;
  background: var(--bg-card);
  border-left: 1px solid var(--border-color);
  overflow-y: auto;
  transition: transform 0.3s ease, opacity 0.3s ease;
  transform: translateX(100%);
  opacity: 0;
}

.detail-panel.show {
  transform: translateX(0);
  opacity: 1;
}

.node-detail {
  padding: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.node-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.close-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.node-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px 0;
}

.node-category {
  display: inline-block;
  padding: 4px 10px;
  background: var(--primary-bg);
  color: var(--primary-color);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.detail-section {
  margin-top: 20px;
}

.detail-section h3 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 10px 0;
}

.detail-section p {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
}

.related-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.related-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.related-item:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
}

.rel-type {
  padding: 2px 8px;
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.rel-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.related-item svg {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.relevance-bar {
  height: 6px;
  background: var(--border-color);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 6px;
}

.relevance-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #059669);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.relevance-text {
  font-size: 13px;
  font-weight: 600;
  color: #10b981;
}

.empty-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  text-align: center;
  padding: 40px;
}

.empty-detail svg {
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-detail p {
  font-size: 14px;
  margin: 0;
}

/* 图例 */
.legend {
  display: flex;
  justify-content: center;
  gap: 24px;
  padding: 12px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

/* 统计栏 */
.stats-bar {
  display: flex;
  justify-content: center;
  gap: 48px;
  padding: 12px 24px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary-color);
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 响应式 */
@media (max-width: 1024px) {
  .detail-panel {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 10;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.2);
  }
}

@media (max-width: 768px) {
  .network-page {
    height: calc(100vh - var(--header-height, 64px) - 32px);
    border-radius: 12px;
  }

  .page-header {
    padding: 12px 16px;
  }

  .page-title {
    font-size: 16px;
  }

  .page-subtitle {
    display: none;
  }

  .detail-panel {
    width: 100%;
  }

  .legend {
    flex-wrap: wrap;
    gap: 12px;
  }

  .stats-bar {
    gap: 24px;
    padding: 10px 16px;
  }

  .stat-value {
    font-size: 16px;
  }

  .stat-label {
    font-size: 12px;
  }
}
</style>
