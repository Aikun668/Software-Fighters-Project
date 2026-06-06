<template>
  <div class="dashboard-container">
    <div class="welcome-section">
      <div class="welcome-card">
        <div class="welcome-content">
          <h1 class="welcome-title">你好，学习者 👋</h1>
          <p class="welcome-desc">今天也要继续加油，让学习效率提升 100%</p>
        </div>
        <div class="welcome-decoration">
          <div class="deco-circle circle-1"></div>
          <div class="deco-circle circle-2"></div>
          <div class="deco-circle circle-3"></div>
        </div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-grid">
        <div class="stat-card" v-for="(stat, index) in statsList" :key="index">
          <div class="stat-card-content">
            <div class="stat-icon" :style="{ background: stat.gradient }">
              <el-icon :size="28"><component :is="stat.icon" /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
            <div class="stat-arrow">
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="recent-learning">
        <el-card class="section-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">最近学习</span>
              <el-button type="primary" link size="small">查看全部</el-button>
            </div>
          </template>
          <div class="recent-list">
            <div v-for="(item, index) in recentItems" :key="index" class="recent-item">
              <div class="item-icon" :style="{ background: item.gradient }">
                <el-icon :size="20"><component :is="item.icon" /></el-icon>
              </div>
              <div class="item-info">
                <div class="item-title">{{ item.title }}</div>
                <div class="item-meta">{{ item.meta }}</div>
              </div>
              <div class="item-progress">
                <div class="mini-progress">
                  <div class="mini-progress-bar" :style="{ width: item.progress + '%' }"></div>
                </div>
                <span class="progress-text">{{ item.progress }}%</span>
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <div class="learning-progress">
        <el-card class="section-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">学习进度</span>
            </div>
          </template>
          <div class="progress-list">
            <div class="progress-item" v-for="(p, index) in progressList" :key="index">
              <div class="progress-header">
                <span class="progress-label">{{ p.label }}</span>
                <span class="progress-percent">{{ p.percent }}%</span>
              </div>
              <el-progress :percentage="p.percent" :stroke-width="10" :color="p.color" :show-text="false" />
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <div class="chart-section">
      <el-card class="section-card">
        <template #header>
          <div class="card-header">
            <span class="card-title">本周学习时长</span>
          </div>
        </template>
        <div class="chart-container">
          <div class="bar-chart">
            <div v-for="(day, index) in weeklyData" :key="index" class="bar-item">
              <div class="bar-wrapper">
                <div class="bar" :style="{ height: day.hours * 24 + 'px' }"></div>
              </div>
              <div class="bar-label">{{ day.day }}</div>
            </div>
          </div>
          <div class="chart-summary">
            <div class="summary-item">
              <span class="summary-label">总时长</span>
              <span class="summary-value">{{ weeklyTotal }}小时</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">日均</span>
              <span class="summary-value">{{ weeklyAverage }}小时</span>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Document, TrendCharts, Clock, Trophy, Files, EditPen, ArrowRight } from '@element-plus/icons-vue';

const statsList = ref([
  { icon: Document, value: 12, label: '已完成课程', gradient: 'linear-gradient(135deg, #C2410C 0%, #EA580C 100%)' },
  { icon: TrendCharts, value: '50%', label: '学习进度', gradient: 'linear-gradient(135deg, #16A34A 0%, #22C55E 100%)' },
  { icon: Clock, value: '86h', label: '累计学习时长', gradient: 'linear-gradient(135deg, #D97706 0%, #F59E0B 100%)' },
  { icon: Trophy, value: '7d', label: '连续学习天数', gradient: 'linear-gradient(135deg, #C2410C 0%, #EA580C 100%)' }
]);

const recentItems = ref([
  { title: '深度学习入门指南', meta: '课程文档 · 今天', progress: 80, icon: Document, gradient: 'linear-gradient(135deg, rgba(194, 65, 12, 0.1) 0%, rgba(234, 88, 12, 0.1) 100%)' },
  { title: '神经网络基础', meta: '课程视频 · 昨天', progress: 100, icon: Files, gradient: 'linear-gradient(135deg, rgba(22, 163, 74, 0.1) 0%, rgba(34, 197, 94, 0.1) 100%)' },
  { title: 'PyTorch实战练习', meta: '习题 · 2天前', progress: 60, icon: EditPen, gradient: 'linear-gradient(135deg, rgba(217, 119, 6, 0.1) 0%, rgba(245, 158, 11, 0.1) 100%)' }
]);

const progressList = ref([
  { label: '整体进度', percent: 50, color: 'linear-gradient(90deg, #C2410C 0%, #EA580C 100%)' },
  { label: '理论学习', percent: 65, color: 'linear-gradient(90deg, #16A34A 0%, #22C55E 100%)' },
  { label: '实践练习', percent: 35, color: 'linear-gradient(90deg, #D97706 0%, #F59E0B 100%)' }
]);

const weeklyData = ref([
  { day: '周一', hours: 2.5 },
  { day: '周二', hours: 3 },
  { day: '周三', hours: 1.5 },
  { day: '周四', hours: 4 },
  { day: '周五', hours: 2 },
  { day: '周六', hours: 5 },
  { day: '周日', hours: 3.5 }
]);

const weeklyTotal = computed(() => weeklyData.value.reduce((sum, d) => sum + d.hours, 0).toFixed(1));
const weeklyAverage = computed(() => (Number(weeklyTotal.value) / 7).toFixed(1));
</script>

<style scoped>
.dashboard-container {
  padding: 0;
}

.welcome-section {
  margin-bottom: 28px;
}

.welcome-card {
  position: relative;
  background: var(--gradient-primary);
  border-radius: 24px;
  padding: 32px;
  overflow: hidden;
  box-shadow: 0 20px 40px rgba(194, 65, 12, 0.25);
}

.welcome-content {
  position: relative;
  z-index: 10;
}

.welcome-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.2;
}

.welcome-desc {
  margin: 8px 0 0 0;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.85);
}

.welcome-decoration {
  position: absolute;
  right: -20px;
  top: -20px;
}

.deco-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
}

.circle-1 {
  width: 120px;
  height: 120px;
  right: 40px;
  top: 20px;
}

.circle-2 {
  width: 80px;
  height: 80px;
  right: 100px;
  top: -10px;
  background: rgba(255, 255, 255, 0.15);
}

.circle-3 {
  width: 50px;
  height: 50px;
  right: 0px;
  top: 50px;
  background: rgba(255, 255, 255, 0.08);
}

.stats-section {
  margin-bottom: 28px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-card {
  background: #ffffff;
  border-radius: 20px;
  padding: 24px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
  cursor: pointer;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.stat-card-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: var(--text-placeholder);
  margin-top: 4px;
}

.stat-arrow {
  color: var(--text-placeholder);
  transition: transform 0.2s ease;
  margin-left: auto;
  display: flex;
  align-items: center;
}

.stat-card:hover .stat-arrow {
  transform: translateX(4px);
}

.content-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
  margin-bottom: 28px;
}

.section-card {
  border-radius: 20px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  transition: all 0.2s ease;
}

.section-card:hover {
  box-shadow: var(--shadow-md);
}

.section-card :deep(.el-card__header) {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.section-card :deep(.el-card__body) {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.recent-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: var(--bg-page);
  border-radius: 14px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.recent-item:hover {
  background: var(--primary-bg);
  transform: translateX(4px);
}

.item-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  flex-shrink: 0;
}

.item-info {
  flex: 1;
  margin-left: 14px;
}

.item-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.item-meta {
  font-size: 13px;
  color: var(--text-placeholder);
}

.item-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mini-progress {
  width: 80px;
  height: 6px;
  background: #E2E8F0;
  border-radius: 4px;
  overflow: hidden;
}

.mini-progress-bar {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.progress-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  color: var(--text-secondary);
}

.progress-percent {
  font-weight: 600;
  color: var(--text-primary);
}

.chart-section {
  margin-bottom: 28px;
}

.chart-container {
  padding: 10px 0;
}

.bar-chart {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 240px;
  padding: 0 30px;
}

.bar-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.bar-wrapper {
  height: 180px;
  display: flex;
  align-items: flex-end;
}

.bar {
  width: 44px;
  background: var(--gradient-primary);
  border-radius: 8px 8px 4px 4px;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(194, 65, 12, 0.15);
}

.bar:hover {
  opacity: 0.8;
  transform: scaleY(1.05);
  transform-origin: bottom;
}

.bar-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.chart-summary {
  display: flex;
  gap: 32px;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-label {
  font-size: 13px;
  color: var(--text-placeholder);
}

.summary-value {
  font-size: 22px;
  font-weight: 700;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .welcome-card {
    padding: 24px;
  }

  .welcome-title {
    font-size: 22px;
  }

  .bar-chart {
    padding: 0 10px;
  }

  .bar {
    width: 32px;
  }
}
</style>
