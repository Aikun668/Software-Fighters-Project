<template>
  <div class="login-register">
    <!-- 背景装饰 -->
    <div class="background">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
    </div>

    <!-- 主容器 -->
    <div class="container">
      <!-- 左侧品牌区域 -->
      <div class="brand-section">
        <div class="brand-logo">
          <SvgIcon name="sparkles" :size="36" color="#ffffff" />
        </div>
        <h1>AI学习平台</h1>
        <p>开启你的AI学习之旅</p>
        <div class="features">
          <div class="feature-item">
            <SvgIcon name="book-open" :size="18" color="#ffffff" />
            <span>丰富的学习资源</span>
          </div>
          <div class="feature-item">
            <SvgIcon name="check-circle" :size="18" color="#ffffff" />
            <span>个性化学习路径</span>
          </div>
          <div class="feature-item">
            <SvgIcon name="message-circle" :size="18" color="#ffffff" />
            <span>智能答疑助手</span>
          </div>
        </div>
      </div>

      <!-- 右侧表单区域 -->
      <div class="form-section">
        <!-- 选项卡切换 -->
        <div class="tabs">
          <button
            :class="['tab-btn', { active: isLogin }]"
            @click="isLogin = true"
          >
            登录
          </button>
          <button
            :class="['tab-btn', { active: !isLogin }]"
            @click="isLogin = false"
          >
            注册
          </button>
        </div>

        <!-- 登录表单 -->
        <el-form v-if="isLogin" :model="loginForm" class="form">
          <h2>欢迎回来</h2>
          <p class="form-desc">请登录你的账号</p>
          
          <el-form-item>
            <el-input v-model="loginForm.phone" placeholder="手机号码">
              <template #prefix>
                <img src="../assets/icons/message-circle.svg" alt="手机号" style="width: 18px; height: 18px;" />
              </template>
            </el-input>
          </el-form-item>
          
          <!-- 密码输入框（密码登录模式） -->
          <el-form-item v-if="!isCaptchaLogin">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="密码"
            >
              <template #prefix>
                <SvgIcon name="lock" :size="18" color="#909399" />
              </template>
            </el-input>
          </el-form-item>
          
          <!-- 验证码输入框（验证码登录模式） -->
          <el-form-item v-else>
            <el-input
              v-model="loginForm.captcha"
              placeholder="验证码"
              @keyup.enter="handleLogin"
            >
              <template #prefix>
                <SvgIcon name="lock" :size="18" color="#909399" />
              </template>
              <template #suffix>
                <button
                  type="button"
                  class="captcha-btn"
                  :disabled="captchaCountdown > 0"
                  @click="sendCaptcha"
                >
                  {{ captchaCountdown > 0 ? `${captchaCountdown}s` : '获取验证码' }}
                </button>
              </template>
            </el-input>
          </el-form-item>
          
          <!-- 登录方式切换 -->
          <div class="login-tabs">
            <button
              :class="['login-tab', { active: !isCaptchaLogin }]"
              @click="switchLoginMode('password')"
            >
              密码登录
            </button>
            <button
              :class="['login-tab', { active: isCaptchaLogin }]"
              @click="switchLoginMode('captcha')"
            >
              验证码登录
            </button>
          </div>
          
          <div class="form-options" v-if="!isCaptchaLogin">
            <label class="checkbox-label">
              <input type="checkbox" v-model="loginForm.remember">
              <span>记住我</span>
            </label>
            <a href="#" class="forgot-link">忘记密码？</a>
          </div>
          
          <el-button type="primary" class="submit-btn" @click="handleLogin" :loading="loading">
            {{ isCaptchaLogin ? '登录' : '登录' }}
          </el-button>
        </el-form>

        <!-- 注册表单 -->
        <el-form v-else :model="registerForm" class="form">
          <h2>创建账号</h2>
          <p class="form-desc">开启你的AI学习之旅</p>
          
          <el-form-item>
            <el-input v-model="registerForm.username" placeholder="用户名">
              <template #prefix>
                <SvgIcon name="user" :size="18" color="#909399" />
              </template>
            </el-input>
          </el-form-item>
          
          <el-form-item>
            <el-input v-model="registerForm.email" placeholder="邮箱地址">
              <template #prefix>
                <SvgIcon name="email" :size="18" color="#909399" />
              </template>
            </el-input>
          </el-form-item>
          
          <el-form-item>
            <el-input
              v-model="registerForm.password"
              type="password"
              placeholder="密码"
            >
              <template #prefix>
                <SvgIcon name="lock" :size="18" color="#909399" />
              </template>
            </el-input>
          </el-form-item>
          
          <el-form-item>
            <el-input
              v-model="registerForm.confirmPassword"
              type="password"
              placeholder="确认密码"
              @keyup.enter="handleRegister"
            >
              <template #prefix>
                <SvgIcon name="lock" :size="18" color="#909399" />
              </template>
            </el-input>
          </el-form-item>
          
          <label class="checkbox-label terms">
            <input type="checkbox" v-model="registerForm.agree">
            <span>我已阅读并同意<a href="#">服务条款</a>和<a href="#">隐私政策</a></span>
          </label>
          
          <el-button type="primary" class="submit-btn" @click="handleRegister" :loading="loading">
            注册
          </el-button>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import SvgIcon from '../components/SvgIcon.vue'

const router = useRouter()

const isLogin = ref(true)
const loading = ref(false)
const captchaCountdown = ref(0)
const isCaptchaLogin = ref(false)

const switchLoginMode = (mode: 'password' | 'captcha') => {
  isCaptchaLogin.value = mode === 'captcha'
}

const loginForm = reactive({
  phone: '',
  password: '',
  captcha: '',
  remember: false
})

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  agree: false
})

const userStore = useUserStore()

const sendCaptcha = async () => {
  if (!loginForm.phone) {
    ElMessage.warning('请先输入手机号码')
    return
  }

  const phoneRegex = /^1[3-9]\d{9}$/
  if (!phoneRegex.test(loginForm.phone)) {
    ElMessage.warning('请输入有效的手机号码')
    return
  }

  try {
    // 发送验证码请求
    // await getCaptcha(loginForm.phone)
    ElMessage.success('验证码已发送到您的手机')
    
    // 开始倒计时
    captchaCountdown.value = 60
    const timer = setInterval(() => {
      captchaCountdown.value--
      if (captchaCountdown.value <= 0) {
        clearInterval(timer)
      }
    }, 1000)
  } catch (error) {
    ElMessage.error('发送验证码失败，请重试')
  }
}

const handleLogin = async () => {
  if (!loginForm.phone) {
    ElMessage.warning('请填写手机号码')
    return
  }
  
  const phoneRegex = /^1[3-9]\d{9}$/
  if (!phoneRegex.test(loginForm.phone)) {
    ElMessage.warning('请输入有效的手机号码')
    return
  }
  
  // 密码登录模式验证
  if (!isCaptchaLogin.value) {
    if (!loginForm.password) {
      ElMessage.warning('请填写密码')
      return
    }
    
    if (loginForm.password.length < 6) {
      ElMessage.warning('密码长度至少为6位')
      return
    }
  } else {
    // 验证码登录模式验证
    if (!loginForm.captcha) {
      ElMessage.warning('请输入验证码')
      return
    }
    
    if (loginForm.captcha.length < 4) {
      ElMessage.warning('验证码长度不正确')
      return
    }
  }
  
  loading.value = true
  
  try {
    await new Promise(resolve => setTimeout(resolve, 800))
    
    userStore.setProfile({
      id: '1',
      name: loginForm.phone,
      avatar: '',
      email: '',
      major: '计算机科学',
      grade: '大三',
      learningGoals: ['人工智能', '机器学习', '深度学习'],
      interests: ['编程', '数据科学', 'AI应用']
    })
    
    if (loginForm.remember) {
      localStorage.setItem('userPhone', loginForm.phone)
    }

    router.replace('/dashboard')

    ElMessage.success('登录成功！')
  } catch (error) {
    console.error('登录跳转失败:', error)
    ElMessage.error('登录失败，请重试')
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!registerForm.username || !registerForm.email || !registerForm.password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(registerForm.email)) {
    ElMessage.warning('请输入有效的邮箱地址')
    return
  }
  
  if (registerForm.password.length < 6) {
    ElMessage.warning('密码长度至少为6位')
    return
  }
  
  if (registerForm.password !== registerForm.confirmPassword) {
    ElMessage.warning('两次密码不一致')
    return
  }
  
  if (!registerForm.agree) {
    ElMessage.warning('请同意服务条款和隐私政策')
    return
  }
  
  loading.value = true
  
  try {
    await new Promise(resolve => setTimeout(resolve, 800))
    
    userStore.setProfile({
      id: '1',
      name: registerForm.username,
      avatar: '',
      email: registerForm.email,
      major: '计算机科学',
      grade: '大一',
      learningGoals: [],
      interests: []
    })
    
    ElMessage.success('注册成功！')

    router.replace('/dashboard')
  } catch (error) {
    ElMessage.error('注册失败，请重试')
  } finally {
    loading.value = false
  }
}

const initForm = () => {
  const savedPhone = localStorage.getItem('userPhone')
  if (savedPhone) {
    loginForm.phone = savedPhone
    loginForm.remember = true
  }
}

initForm()
</script>

<style scoped>
.login-register {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #C2410C 0%, #EA580C 50%, #F59E0B 100%);
  position: relative;
  overflow: hidden;
}

.background {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.3;
}

.bg-circle-1 {
  width: 400px;
  height: 400px;
  background: rgba(251, 146, 60, 0.4);
  top: -100px;
  left: -100px;
  animation: float 6s ease-in-out infinite;
}

.bg-circle-2 {
  width: 300px;
  height: 300px;
  background: rgba(245, 158, 11, 0.4);
  bottom: -50px;
  right: -50px;
  animation: float 8s ease-in-out infinite reverse;
}

.bg-circle-3 {
  width: 200px;
  height: 200px;
  background: rgba(234, 88, 12, 0.3);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: float 4s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
}

.container {
  display: flex;
  width: 900px;
  height: 500px;
  background-color: var(--card-bg);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.brand-section {
  width: 40%;
  padding: 40px;
  background: linear-gradient(135deg, #C2410C 0%, #EA580C 100%);
  color: white;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.brand-logo {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  margin-bottom: 20px;
}

.brand-section h1 {
  margin: 0 0 8px 0;
  font-size: 28px;
}

.brand-section p {
  margin: 0 0 30px 0;
  opacity: 0.9;
}

.features {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
}

.form-section {
  width: 60%;
  padding: 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.tabs {
  display: flex;
  margin-bottom: 24px;
}

.tab-btn {
  flex: 1;
  padding: 12px;
  border: none;
  background-color: transparent;
  font-size: 16px;
  font-weight: 500;
  color: #909399;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}

.tab-btn.active {
  color: #C2410C;
  border-bottom-color: #C2410C;
}

.login-tabs {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
  padding: 4px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 8px;
}

.login-tab {
  flex: 1;
  padding: 10px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}

.login-tab.active {
  background: #ffffff;
  color: #C2410C;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.form h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #303133;
}

.form-desc {
  margin: 0 0 24px 0;
  color: #909399;
  font-size: 14px;
}

.form {
  width: 100%;
}

.form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.form :deep(.el-input) {
  height: 44px;
}

.form :deep(.el-input__inner) {
  border-radius: 8px;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
  cursor: pointer;
}

.checkbox-label input {
  width: 14px;
  height: 14px;
}

.forgot-link {
  font-size: 13px;
  color: #C2410C;
  text-decoration: none;
}

.forgot-link:hover {
  text-decoration: underline;
}

.submit-btn {
  width: 100%;
  height: 44px;
  border-radius: 8px;
  font-size: 15px;
  margin-bottom: 16px;
}

.captcha-btn {
  padding: 0 12px;
  height: 28px;
  font-size: 12px;
  color: #C2410C;
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.captcha-btn:hover:not(:disabled) {
  background: rgba(194, 65, 12, 0.1);
}

.captcha-btn:disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}

.divider {
  display: flex;
  align-items: center;
  margin: 16px 0;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background-color: var(--border-light);
}

.divider span {
  padding: 0 16px;
  color: var(--text-light);
  font-size: 13px;
}

.social-login {
  display: flex;
  gap: 12px;
}

.social-btn {
  flex: 1;
  height: 40px;
  border-radius: 8px;
  background-color: var(--bg-light);
  border-color: var(--border-light);
  color: var(--text-secondary);
}

.social-btn:hover {
  background-color: rgba(18, 46, 138, 0.1);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.terms {
  margin-bottom: 20px;
}

.terms a {
  color: #C2410C;
  text-decoration: none;
}

.terms a:hover {
  text-decoration: underline;
}
</style>
