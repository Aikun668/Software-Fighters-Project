<template>
  <div class="dashboard-container">
    <div class="welcome-section">
      <div class="welcome-card">
        <div class="welcome-content">
          <h1 class="welcome-title">你好，学习者</h1>
          <p class="welcome-desc">今天也要继续加油，让学习效率提升 100%</p>
        </div>
        <div class="welcome-decoration">
          <svg class="deco-icon" viewBox="0 0 24 24" width="120" height="120" fill="none" stroke="currentColor" stroke-width="1">
            <path d="M12 2L2 7l10 5 10-5-10-5z" opacity="0.3"/>
            <path d="M2 17l10 5 10-5" opacity="0.5"/>
            <path d="M2 12l10 5 10-5" opacity="0.7"/>
          </svg>
        </div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-grid">
        <div class="stat-card" v-for="(stat, index) in statsList" :key="index">
          <div class="stat-card-content">
            <div class="stat-icon" :style="{ background: stat.gradient }">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
                <path v-if="stat.iconType === 'document'" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline v-if="stat.iconType === 'document'" points="14 2 14 8 20 8"/>
                <g v-if="stat.iconType === 'chart'">
                  <line x1="18" y1="20" x2="18" y2="10"/>
                  <line x1="12" y1="20" x2="12" y2="4"/>
                  <line x1="6" y1="20" x2="6" y2="14"/>
                </g>
                <circle v-if="stat.iconType === 'clock'" cx="12" cy="12" r="10"/>
                <polyline v-if="stat.iconType === 'clock'" points="12 6 12 12 16 14"/>
                <path v-if="stat.iconType === 'trophy'" d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/>
                <path v-if="stat.iconType === 'trophy'" d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>
                <path v-if="stat.iconType === 'trophy'" d="M4 22h16"/>
                <path v-if="stat.iconType === 'trophy'" d="M10 22V8a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v14"/>
              </svg>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="recent-learning">
        <div class="section-card">
          <div class="card-header">
            <span class="card-title">最近学习</span>
            <button class="link-btn">查看全部</button>
          </div>
          <div class="recent-list">
            <div v-for="(item, index) in recentItems" :key="index" class="recent-item">
              <div class="item-icon" :style="{ background: item.gradient }">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
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
        </div>
      </div>

      <div class="learning-progress">
        <div class="section-card">
          <div class="card-header">
            <span class="card-title">学习进度</span>
          </div>
          <div class="progress-list">
            <div class="progress-item" v-for="(p, index) in progressList" :key="index">
              <div class="progress-header">
                <span class="progress-label">{{ p.label }}</span>
                <span class="progress-percent">{{ p.percent }}%</span>
              </div>
              <div class="progress-bar">
                <div class="progress-bar-fill" :style="{ width: p.percent + '%', background: p.color }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="chart-section">
      <div class="section-card">
        <div class="card-header">
          <span class="card-title">本周学习时长</span>
        </div>
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const statsList = ref([
  { iconType: 'document', value: 12, label: '已完成课程', gradient: 'linear-gradient(135deg, #22C55E 0%, #16A34A 100%)' },
  { iconType: 'chart', value: '50%', label: '学习进度', gradient: 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)' },
  { iconType: 'clock', value: '86h', label: '累计学习时长', gradient: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)' },
  { iconType: 'trophy', value: '7d', label: '连续学习天数', gradient: 'linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%)' }
]);

const recentItems = ref([
  { title: '深度学习入门指南', meta: '课程文档 · 今天', progress: 80, gradient: 'linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(22, 163, 74, 0.15) 100%)' },
  { title: '神经网络基础', meta: '课程视频 · 昨天', progress: 100, gradient: 'linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(37, 99, 235, 0.15) 100%)' },
  { title: 'PyTorch实战练习', meta: '习题 · 2天前', progress: 60, gradient: 'linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(217, 119, 6, 0.15) 100%)' }
]);

const progressList = ref([
  { label: '整体进度', percent: 50, color: 'linear-gradient(90deg, #22C55E 0%, #16A34A 100%)' },
  { label: '理论学习', percent: 65, color: 'linear-gradient(90deg, #3B82F6 0%, #2563EB 100%)' },
  { label: '实践练习', percent: 35, color: 'linear-gradient(90deg, #F59E0B 0%, #D97706 100%)' }
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
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
  border: 1px solid var(--border-color);
  border-radius: 24px;
  padding: 32px;
  overflow: hidden;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.welcome-content {
  position: relative;
  z-index: 10;
}

.welcome-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.welcome-desc {
  margin: 8px 0 0 0;
  font-size: 16px;
  color: var(--text-secondary);
}

.welcome-decoration {
  position: absolute;
  right: -10px;
  top: -10px;
}

.deco-icon {
  color: var(--primary-color);
  opacity: 0.3;
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
  background: var(--bg-card);
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
  border-color: var(--primary-color);
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
  flex-shrink: 0;
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
  color: var(--text-secondary);
  margin-top: 4px;
}

.content-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
  margin-bottom: 28px;
}

.section-card {
  background: var(--bg-card);
  border-radius: 20px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  padding: 24px;
  transition: all 0.2s ease;
}

.section-card:hover {
  box-shadow: var(--shadow-md);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.link-btn {
  background: none;
  border: none;
  color: var(--primary-color);
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s ease;
}

.link-btn:hover {
  color: var(--primary-light);
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
  background: var(--card-bg);
  border-radius: 14px;
  transition: all 0.2s ease;
  cursor: pointer;
  border: 1px solid transparent;
}

.recent-item:hover {
  background: var(--primary-bg);
  border-color: var(--primary-color);
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
  color: var(--text-secondary);
}

.item-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mini-progress {
  width: 80px;
  height: 6px;
  background: var(--border-color);
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

.progress-bar {
  height: 10px;
  background: var(--border-color);
  border-radius: 5px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.5s ease;
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
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.2);
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
  color: var(--text-secondary);
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
