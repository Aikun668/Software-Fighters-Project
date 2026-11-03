<template>
  <div class="exercise-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-info">
        <h1>在线答题</h1>
        <p>{{ currentExercise.title }}</p>
      </div>
      <div class="header-stats">
        <span class="stat-item">
          <el-icon icon="Clock" />
          {{ timeRemaining }}
        </span>
        <span class="stat-item">
          <el-icon icon="FileText" />
          {{ currentIndex + 1 }} / {{ questions.length }}
        </span>
        <span class="stat-item">
          <el-icon icon="CheckCircle" />
          {{ correctCount }} 正确
        </span>
      </div>
    </div>

    <!-- 题目区域 -->
    <div class="question-container">
      <!-- 选择题 -->
      <div v-if="currentQuestion.type === 'choice'" class="question-card">
        <div class="question-header">
          <span class="question-type">选择题</span>
          <span class="question-score">（{{ currentQuestion.score }}分）</span>
        </div>
        <h2 class="question-title">{{ currentQuestion.question }}</h2>
        <div class="options-list">
          <div
            v-for="(option, index) in currentQuestion.options"
            :key="index"
            :class="[
              'option-item',
              selectedAnswer === index ? 'selected' : '',
              showResult ? (index === currentQuestion.correctAnswer ? 'correct' : (selectedAnswer === index ? 'wrong' : '')) : ''
            ]"
            @click="selectOption(index)"
          >
            <span class="option-label">{{ String.fromCharCode(65 + index) }}</span>
            <span class="option-text">{{ option }}</span>
            <el-icon v-if="showResult && index === currentQuestion.correctAnswer" class="option-icon correct-icon">
              <Check />
            </el-icon>
            <el-icon v-if="showResult && selectedAnswer === index && index !== currentQuestion.correctAnswer" class="option-icon wrong-icon">
              <Close />
            </el-icon>
          </div>
        </div>
      </div>

      <!-- 填空题 -->
      <div v-else-if="currentQuestion.type === 'fill'" class="question-card">
        <div class="question-header">
          <span class="question-type">填空题</span>
          <span class="question-score">（{{ currentQuestion.score }}分）</span>
        </div>
        <h2 class="question-title">{{ currentQuestion.question }}</h2>
        <div class="fill-input">
          <el-input
            v-model="fillAnswer"
            :disabled="showResult"
            placeholder="请输入答案"
          ></el-input>
        </div>
      </div>

      <!-- 简答题 -->
      <div v-else-if="currentQuestion.type === 'essay'" class="question-card">
        <div class="question-header">
          <span class="question-type">简答题</span>
          <span class="question-score">（{{ currentQuestion.score }}分）</span>
        </div>
        <h2 class="question-title">{{ currentQuestion.question }}</h2>
        <div class="essay-input">
          <el-input
            type="textarea"
            :rows="6"
            v-model="essayAnswer"
            :disabled="showResult"
            placeholder="请输入你的回答"
          ></el-input>
        </div>
      </div>

      <!-- 编程题 -->
      <div v-else-if="currentQuestion.type === 'code'" class="question-card">
        <div class="question-header">
          <span class="question-type">编程题</span>
          <span class="question-score">（{{ currentQuestion.score }}分）</span>
        </div>
        <h2 class="question-title">{{ currentQuestion.question }}</h2>
        <div class="code-hints" v-if="currentQuestion.hints">
          <h4>提示：</h4>
          <ul>
            <li v-for="(hint, index) in currentQuestion.hints" :key="index">{{ hint }}</li>
          </ul>
        </div>
        <div class="code-editor">
          <div class="editor-header">
            <span>main.py</span>
            <el-button size="small" @click="resetCode">
              <el-icon icon="Refresh" />
              重置
            </el-button>
          </div>
          <textarea
            v-model="codeAnswer"
            :disabled="showResult"
            class="code-textarea"
            placeholder="在这里编写代码..."
          ></textarea>
        </div>
      </div>

      <!-- 答案解析 -->
      <div v-if="showResult" class="result-panel">
        <div :class="['result-header', isCorrect ? 'correct' : 'wrong']">
          <el-icon>{{ isCorrect ? CheckCircle : XCircle }}</el-icon>
          <span>{{ isCorrect ? '回答正确！' : '回答错误' }}</span>
        </div>
        <div v-if="gradeFeedback" class="feedback">
          <h4>AI 反馈：</h4>
          <p>{{ gradeFeedback }}</p>
        </div>
        <div class="analysis">
          <h4>答案解析：</h4>
          <p>{{ currentQuestion.analysis }}</p>
        </div>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div class="action-bar">
      <el-button
        v-if="currentIndex > 0"
        @click="prevQuestion"
        :disabled="showResult"
      >
        <el-icon icon="ArrowLeft" />
        上一题
      </el-button>
      <div class="question-nav">
        <div
          v-for="(q, index) in questions"
          :key="index"
          :class="[
            'nav-item',
            index === currentIndex ? 'active' : '',
            answeredQuestions.includes(index) ? 'answered' : ''
          ]"
          @click="goToQuestion(index)"
        >
          {{ index + 1 }}
        </div>
      </div>
      <el-button
        v-if="!showResult"
        type="primary"
        @click="submitAnswer"
        :disabled="!isAnswerValid || isGrading"
      >
        <span v-if="isGrading">评分中...</span>
        <span v-else>提交答案</span>
      </el-button>
      <el-button
        v-else-if="currentIndex < questions.length - 1"
        type="primary"
        @click="nextQuestion"
      >
        下一题
        <el-icon icon="ArrowRight" />
      </el-button>
      <el-button
        v-else
        type="success"
        @click="showFinalResult"
      >
        <el-icon icon="Trophy" />
        查看成绩
      </el-button>
    </div>

    <!-- 成绩弹窗 -->
    <el-dialog
      title="答题完成"
      :visible="showFinalDialog"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="final-result">
        <div class="score-circle">
          <span class="score-value">{{ finalScore }}</span>
          <span class="score-label">分</span>
        </div>
        <div class="result-stats">
          <div class="stat-row">
            <span class="stat-label">正确题数</span>
            <span class="stat-value correct">{{ correctCount }} / {{ questions.length }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">正确率</span>
            <span class="stat-value">{{ Math.round((correctCount / questions.length) * 100) }}%</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">用时</span>
            <span class="stat-value">{{ formatTime(usedTime) }}</span>
          </div>
        </div>
        <div class="result-message">{{ getResultMessage() }}</div>
      </div>
      <template #footer>
        <el-button @click="restart">重新答题</el-button>
        <el-button type="primary" @click="closeFinalDialog">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

interface Question {
  id: string
  type: 'choice' | 'fill' | 'essay' | 'code'
  question: string
  options?: string[]
  correctAnswer: number | string
  score: number
  analysis: string
  hints?: string[]
}

const currentExercise = ref({
  title: '机器学习基础测试'
})

const questions = ref<Question[]>([
  {
    id: '1',
    type: 'choice',
    question: '以下哪个不是监督学习算法？',
    options: ['线性回归', '决策树', 'K-Means', '支持向量机'],
    correctAnswer: 2,
    score: 10,
    analysis: 'K-Means是一种无监督学习算法，用于聚类分析。其他选项都是监督学习算法。'
  },
  {
    id: '2',
    type: 'fill',
    question: '神经网络中，______函数用于将输出值压缩到0到1之间。',
    correctAnswer: 'sigmoid',
    score: 10,
    analysis: 'Sigmoid函数的公式是 σ(x) = 1 / (1 + e^(-x))，它可以将任意实数映射到(0, 1)区间。'
  },
  {
    id: '3',
    type: 'choice',
    question: '在深度学习中，ReLU激活函数的主要优点是什么？',
    options: ['计算速度快', '避免梯度消失', '输出范围有限', '以上都是'],
    correctAnswer: 3,
    score: 10,
    analysis: 'ReLU函数计算简单（max(0, x)），相比sigmoid和tanh能有效缓解梯度消失问题，且输出范围是非负的。'
  },
  {
    id: '4',
    type: 'essay',
    question: '请简述过拟合的概念以及如何防止过拟合。',
    correctAnswer: '',
    score: 20,
    analysis: '过拟合是指模型在训练集上表现很好，但在测试集上表现很差的现象。防止过拟合的方法包括：1) 使用更多的数据；2) 添加正则化（L1、L2）；3) 使用Dropout；4) 早停；5) 减少模型复杂度。'
  },
  {
    id: '5',
    type: 'code',
    question: '请实现一个简单的线性回归预测函数。',
    correctAnswer: '',
    score: 30,
    analysis: '线性回归的预测公式是 y = wx + b。可以使用NumPy实现矩阵运算。',
    hints: [
      '使用numpy进行计算',
      '预测公式：y_pred = X @ w + b',
      '注意矩阵维度匹配'
    ]
  },
  {
    id: '6',
    type: 'choice',
    question: '以下关于卷积神经网络（CNN）的说法，哪个是正确的？',
    options: ['CNN只能处理图像数据', '池化层用于增加特征图尺寸', '卷积层用于提取局部特征', '全连接层在卷积层之前'],
    correctAnswer: 2,
    score: 10,
    analysis: '卷积层通过卷积操作提取图像的局部特征，这是CNN的核心。CNN也可以处理其他网格状数据；池化层用于降采样；全连接层通常在卷积层之后。'
  }
])

const currentIndex = ref(0)
const selectedAnswer = ref<number | null>(null)
const fillAnswer = ref('')
const essayAnswer = ref('')
const codeAnswer = ref('')
const showResult = ref(false)
const showFinalDialog = ref(false)
const answeredQuestions = ref<number[]>([])
const correctCount = ref(0)
const startTime = ref(Date.now())
const usedTime = ref(0)
const timeRemaining = ref('30:00')
const isGrading = ref(false)
const gradeFeedback = ref('')

let timer: number | null = null

const currentQuestion = computed(() => questions.value[currentIndex.value])

const isCorrect = computed(() => {
  if (!showResult.value) return false
  if (currentQuestion.value.type === 'choice') {
    return selectedAnswer.value === currentQuestion.value.correctAnswer
  }
  if (currentQuestion.value.type === 'fill') {
    return fillAnswer.value.toLowerCase().trim() === (currentQuestion.value.correctAnswer as string).toLowerCase().trim()
  }
  return true
})

const isAnswerValid = computed(() => {
  if (currentQuestion.value.type === 'choice') {
    return selectedAnswer.value !== null
  }
  if (currentQuestion.value.type === 'fill') {
    return fillAnswer.value.trim() !== ''
  }
  if (currentQuestion.value.type === 'essay') {
    return essayAnswer.value.trim() !== ''
  }
  if (currentQuestion.value.type === 'code') {
    return codeAnswer.value.trim() !== ''
  }
  return false
})

const finalScore = computed(() => {
  return questions.value.reduce((sum, q, index) => {
    if (answeredQuestions.value.includes(index)) {
      if (q.type === 'choice') {
        const answers: Record<number, number | null> = {}
        return sum + q.score
      }
      return sum + Math.round(q.score * 0.8)
    }
    return sum
  }, 0)
})

const selectOption = (index: number) => {
  if (!showResult.value) {
    selectedAnswer.value = index
  }
}

const submitAnswer = async () => {
  isGrading.value = true
  
  const answerData = {
    question_id: currentQuestion.value.id,
    question_type: currentQuestion.value.type,
    answer: getCurrentAnswer()
  }
  
  try {
    const response = await fetch('/exercise/grade', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(answerData)
    })
    
    const result = await response.json()
    
    showResult.value = true
    gradeFeedback.value = result.feedback || ''
    
    if (!answeredQuestions.value.includes(currentIndex.value)) {
      answeredQuestions.value.push(currentIndex.value)
      if (result.correct) {
        correctCount.value++
      }
    }
  } catch (error) {
    console.error('评分失败:', error)
    ElMessage.error('评分失败，请重试')
    
    showResult.value = true
    if (!answeredQuestions.value.includes(currentIndex.value)) {
      answeredQuestions.value.push(currentIndex.value)
      if (isCorrect.value) {
        correctCount.value++
      }
    }
  } finally {
    isGrading.value = false
  }
}

const getCurrentAnswer = () => {
  if (currentQuestion.value.type === 'choice') {
    return String.fromCharCode(65 + (selectedAnswer.value || 0))
  }
  if (currentQuestion.value.type === 'fill') {
    return fillAnswer.value
  }
  if (currentQuestion.value.type === 'essay') {
    return essayAnswer.value
  }
  if (currentQuestion.value.type === 'code') {
    return codeAnswer.value
  }
  return ''
}

const nextQuestion = () => {
  if (currentIndex.value < questions.value.length - 1) {
    currentIndex.value++
    resetAnswers()
    showResult.value = false
  }
}

const prevQuestion = () => {
  if (currentIndex.value > 0) {
    currentIndex.value--
    showResult.value = false
  }
}

const goToQuestion = (index: number) => {
  if (!showResult.value) {
    currentIndex.value = index
    resetAnswers()
  }
}

const resetAnswers = () => {
  selectedAnswer.value = null
  fillAnswer.value = ''
  essayAnswer.value = ''
  codeAnswer.value = ''
}

const resetCode = () => {
  codeAnswer.value = ''
}

const showFinalResult = () => {
  usedTime.value = Date.now() - startTime.value
  showFinalDialog.value = true
}

const closeFinalDialog = () => {
  showFinalDialog.value = false
}

const restart = () => {
  currentIndex.value = 0
  correctCount.value = 0
  answeredQuestions.value = []
  resetAnswers()
  showResult.value = false
  showFinalDialog.value = false
  startTime.value = Date.now()
}

const formatTime = (ms: number) => {
  const seconds = Math.floor(ms / 1000)
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

const getResultMessage = () => {
  const rate = correctCount.value / questions.value.length
  if (rate >= 0.9) return '太棒了！你掌握得很好！'
  if (rate >= 0.7) return '不错！继续加油！'
  if (rate >= 0.5) return '还需要多练习，再接再厉！'
  return '建议复习相关知识点后再试一次。'
}

onMounted(() => {
  timer = window.setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime.value) / 1000)
    const remaining = Math.max(0, 1800 - elapsed)
    const mins = Math.floor(remaining / 60)
    const secs = remaining % 60
    timeRemaining.value = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
})
</script>

<style scoped>
.exercise-page {
  min-height: 100vh;
  background-color: var(--bg-color);
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: var(--primary-color);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.header-info h1 {
  margin: 0 0 4px 0;
  font-size: 18px;
  color: var(--bg-color);
}

.header-info p {
  margin: 0;
  font-size: 13px;
  color: var(--bg-dark);
}

.header-stats {
  display: flex;
  gap: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--bg-color);
}

.question-container {
  flex: 1;
  padding: 24px;
}

.question-card {
  background-color: var(--card-bg);
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
}

.question-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.question-type {
  background-color: var(--primary-color);
  color: white;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
}

.question-score {
  font-size: 14px;
  color: var(--text-light);
}

.question-title {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 500;
  line-height: 1.6;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  border: 2px solid #e4e7ed;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.option-item:hover {
  border-color: var(--primary-color);
  background-color: var(--bg-light);
}

.option-item.selected {
  border-color: var(--primary-color);
  background-color: rgba(18, 46, 138, 0.1);
}

.option-item.correct {
  border-color: var(--success-color);
  background-color: rgba(103, 194, 58, 0.1);
}

.option-item.wrong {
  border-color: var(--error-color);
  background-color: rgba(245, 108, 108, 0.1);
}

.option-label {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: var(--bg-light);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  margin-right: 12px;
}

.option-item.selected .option-label {
  background-color: var(--primary-color);
  color: white;
}

.option-item.correct .option-label {
  background-color: var(--success-color);
  color: white;
}

.option-item.wrong .option-label {
  background-color: var(--error-color);
  color: white;
}

.option-text {
  flex: 1;
  font-size: 15px;
}

.option-icon {
  font-size: 18px;
}

.correct-icon {
  color: var(--success-color);
}

.wrong-icon {
  color: var(--error-color);
}

.fill-input {
  max-width: 400px;
}

.fill-input :deep(.el-input) {
  height: 44px;
  font-size: 16px;
}

.essay-input {
  max-width: 100%;
}

.essay-input :deep(.el-textarea) {
  font-size: 15px;
}

.code-hints {
  background-color: #fafafa;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.code-hints h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
}

.code-hints ul {
  margin: 0;
  padding-left: 20px;
}

.code-hints li {
  margin: 6px 0;
  font-size: 14px;
  color: #606266;
}

.code-editor {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-size: 13px;
}

.code-textarea {
  width: 100%;
  height: 200px;
  padding: 14px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 14px;
  line-height: 1.5;
  border: none;
  resize: vertical;
  background-color: #1e1e1e;
  color: #d4d4d4;
}

.code-textarea:focus {
  outline: none;
}

.result-panel {
  margin-top: 20px;
  padding: 20px;
  background-color: #fafafa;
  border-radius: 10px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 600;
}

.result-header.correct {
  color: #67c23a;
}

.result-header.wrong {
  color: #f56c6c;
}

.analysis h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
}

.analysis p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #606266;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: white;
  border-top: 1px solid #e4e7ed;
}

.question-nav {
  display: flex;
  gap: 8px;
}

.nav-item {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background-color: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-item:hover {
  background-color: #e4e7ed;
}

.nav-item.active {
  background-color: #409eff;
  color: white;
}

.nav-item.answered {
  background-color: #e8f4fd;
  border: 1px solid #409eff;
}

.final-result {
  text-align: center;
}

.score-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #67c23a);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
}

.score-value {
  font-size: 36px;
  font-weight: 600;
  color: white;
}

.score-label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.8);
}

.result-stats {
  margin-bottom: 20px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f2f6fc;
}

.stat-label {
  color: #909399;
}

.stat-value {
  font-weight: 600;
}

.stat-value.correct {
  color: #67c23a;
}

.result-message {
  padding: 16px;
  background-color: #f5f7fa;
  border-radius: 8px;
  font-size: 14px;
  color: #606266;
}
</style>
