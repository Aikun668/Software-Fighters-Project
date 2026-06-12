<template>
  <div class="login-register">
    <!-- 背景装饰 -->
    <div class="background">
      <div class="bg-grid"></div>
      <div class="bg-glow bg-glow-1"></div>
      <div class="bg-glow bg-glow-2"></div>
    </div>

    <!-- 主容器 -->
    <div class="container">
      <!-- 左侧品牌区域 -->
      <div class="brand-section">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <h1>智学云</h1>
        <p>DeepTutor 智能学习系统</p>
        <div class="features">
          <div class="feature-item">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
            <span>丰富的学习资源</span>
          </div>
          <div class="feature-item">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span>个性化学习路径</span>
          </div>
          <div class="feature-item">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
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
            @click="switchTab(true)"
          >
            登录
          </button>
          <button
            :class="['tab-btn', { active: !isLogin }]"
            @click="switchTab(false)"
          >
            注册
          </button>
        </div>

        <!-- 登录表单 -->
        <el-form v-if="isLogin" :model="loginForm" class="form">
          <h2>欢迎回来</h2>
          <p class="form-desc">请登录你的账号</p>

          <el-form-item>
            <el-input v-model="loginForm.username" placeholder="用户名">
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <!-- 密码输入框（密码登录模式） -->
          <el-form-item v-if="!isCaptchaLogin">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="密码"
              @keyup.enter="handleLogin"
            >
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <!-- 验证码输入框（验证码登录模式） -->
          <el-form-item v-else>
            <div class="captcha-input-wrapper">
              <el-input
                v-model="loginForm.captcha"
                placeholder="验证码"
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                </template>
              </el-input>
              <div class="captcha-image-wrapper" @click="refreshCaptcha('login')">
                <img 
                  v-if="captchaImage" 
                  :src="captchaImage" 
                  alt="验证码" 
                  class="captcha-image"
                  @error="handleCaptchaError"
                />
                <div v-else class="captcha-loading">
                  <div class="loading-spinner"></div>
                </div>
              </div>
            </div>
          </el-form-item>

          <!-- 登录方式切换 -->
          <div class="login-tabs">
            <button
              type="button"
              :class="['login-tab', { active: !isCaptchaLogin }]"
              @click="switchLoginMode('password')"
            >
              密码登录
            </button>
            <button
              type="button"
              :class="['login-tab', { active: isCaptchaLogin }]"
              @click="switchLoginMode('captcha')"
            >
              验证码登录
            </button>
          </div>

          <div class="form-options">
            <label class="checkbox-label">
              <input type="checkbox" v-model="loginForm.remember">
              <div class="checkbox-text">记住我</div>
            </label>
            <a href="#" class="forgot-link" v-if="!isCaptchaLogin">忘记密码？</a>
          </div>

          <el-button type="primary" class="submit-btn" @click="handleLogin" :loading="loading">
            {{ isCaptchaLogin ? '登录' : '登录' }}
          </el-button>
        </el-form>

        <!-- 注册表单 -->
        <el-form v-else :model="registerForm" class="form">
          <h2>创建账号</h2>
          <p class="form-desc">开启你的 AI 学习之旅</p>

          <el-form-item>
            <el-input v-model="registerForm.username" placeholder="用户名">
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item>
            <el-input v-model="registerForm.phone" placeholder="手机号码">
              <template #prefix>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
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
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
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
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </template>
            </el-input>
          </el-form-item>

          <!-- 验证码 -->
          <el-form-item>
            <div class="captcha-input-wrapper">
              <el-input
                v-model="registerForm.captcha"
                placeholder="验证码"
                @keyup.enter="handleRegister"
              >
                <template #prefix>
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                </template>
              </el-input>
              <div class="captcha-image-wrapper" @click="refreshCaptcha('register')">
                <img 
                  v-if="registerCaptchaImage" 
                  :src="registerCaptchaImage" 
                  alt="验证码" 
                  class="captcha-image"
                  @error="handleRegisterCaptchaError"
                />
                <div v-else class="captcha-loading">
                  <div class="loading-spinner"></div>
                </div>
              </div>
            </div>
          </el-form-item>

          <label class="checkbox-label terms">
            <input type="checkbox" v-model="registerForm.agree">
            <div class="checkbox-text">我已阅读并同意<a href="#">服务条款</a>和<a href="#">隐私政策</a></div>
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
import { login, register } from '@/api/user'
import type { UserLoginRequest, UserRegisterRequest } from '@/api/types'


const router = useRouter()

const isLogin = ref(true)
const loading = ref(false)
const captchaImage = ref('')
const registerCaptchaImage = ref('')
const isCaptchaLogin = ref(false)

const switchLoginMode = (mode: 'password' | 'captcha') => {
  isCaptchaLogin.value = mode === 'captcha'
  if (mode === 'password') {
    loginForm.captcha = ''
  } else {
    loginForm.password = ''
    refreshCaptcha('login')
  }
}

const switchTab = (login: boolean) => {
  isLogin.value = login
  if (!login) {
    refreshCaptcha('register')
  }
}

const loginForm = reactive({
  username: '',
  password: '',
  captcha: '',
  remember: false
})

const registerForm = reactive({
  username: '',
  phone: '',
  password: '',
  confirmPassword: '',
  captcha: '',
  agree: false
})

const userStore = useUserStore()

const isCaptchaLoading = ref(false)

const CaptchaKey = ref('')
const refreshCaptcha = async (type: 'login' | 'register' = 'login') => {
  if (isCaptchaLoading.value) return
  
  isCaptchaLoading.value = true
  
  try {
    const timestamp = Date.now()
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/user/captcha?timestamp=${timestamp}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    
    const data = await response.json()
    
    if (!data || !data.data) {
      ElMessage.error('获取验证码失败：数据格式错误')
      return
    }
    
    if (data.message === 'ok' && data.data.captchaImage) {
      const imageSrc = data.data.captchaImage
      CaptchaKey.value = data.data.captchaKey
      if (type === 'login') {
        captchaImage.value = ''
        setTimeout(() => {
          captchaImage.value = imageSrc
        }, 50)
      } else {
        registerCaptchaImage.value = ''
        setTimeout(() => {
          registerCaptchaImage.value = imageSrc
        }, 50)
      }
    } else {
      ElMessage.error('获取验证码失败：' + (data.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('获取验证码失败:', error)
    ElMessage.warning('验证码加载失败，请点击刷新重试')
    
    
  } finally {
    isCaptchaLoading.value = false
  }
}
// 验证码加载失败处理
const handleCaptchaError = () => {
  captchaImage.value = ''
  ElMessage.warning('验证码加载失败，请点击刷新重试')
}
// 注册验证码加载失败处理
const handleRegisterCaptchaError = () => {
  registerCaptchaImage.value = ''
  ElMessage.warning('验证码加载失败，请点击刷新重试')
}
// 发送验证码
const sendCaptcha = async () => {
  ElMessage.info('图片验证码无需发送，请直接输入图片中的验证码')
}
// 登录
const handleLogin = async () => {
  // 增加一个去除用户名首尾空格的逻辑
  loginForm.username = loginForm.username.trim()


  if (!loginForm.username) {
    ElMessage.warning('请填写用户名')
    return
  }

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
    if (!loginForm.captcha) {
      ElMessage.warning('请输入验证码')
      return
    }

    if (loginForm.captcha.length !== 4) {
      ElMessage.warning('验证码为4位，请正确输入')
      return
    }
  }

  loading.value = true

  try {
    const loginData: UserLoginRequest = {
      username: loginForm.username,
      password: loginForm.password,
      ...(isCaptchaLogin.value ? { code: loginForm.captcha } : { password: loginForm.password })
    }

    const res = await login(loginData)
    console.log(res)

    
    
    userStore.setProfile({
      //@ts-ignore
      id: res,
      userName: loginForm.username,
      avatar: '',
    })

    if (loginForm.remember) {
      localStorage.setItem('username', loginForm.username)
    }

    router.replace('/dashboard')

    ElMessage.success('登录成功！')
  } catch (error: any) {
    console.error('登录失败:', error)
    ElMessage.error(error.message || '登录失败，请重试')
  } finally {
    loading.value = false
  }
}
// 注册
const handleRegister = async () => {
  // 增加一个去除用户名首尾空格的逻辑
  registerForm.username = registerForm.username.trim()
  registerForm.phone = registerForm.phone.trim()
  registerForm.password = registerForm.password.trim()
  registerForm.confirmPassword = registerForm.confirmPassword.trim()
  registerForm.captcha = registerForm.captcha.trim()
  
  if (!registerForm.username || !registerForm.phone || !registerForm.password) {
    ElMessage.warning('请填写完整信息')
    return
  }

  const phoneRegex = /^1[3-9]\d{9}$/
  if (!phoneRegex.test(registerForm.phone)) {
    ElMessage.warning('请输入有效的手机号码')
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

  if (!registerForm.captcha) {
    ElMessage.warning('请输入验证码')
    return
  }

  if (registerForm.captcha.length !== 4) {
    ElMessage.warning('验证码为4位，请正确输入')
    return
  }

  if (!registerForm.agree) {
    ElMessage.warning('请同意服务条款和隐私政策')
    return
  }

  loading.value = true

  try {
    const registerData: UserRegisterRequest = {
      phone: registerForm.phone,
      captchaKey: CaptchaKey.value,
      captchaCode: registerForm.captcha,
      password: registerForm.password,
      passwordConfirm: registerForm.confirmPassword,
      username: registerForm.username
    }

    await register(registerData)

    userStore.setProfile({
      id: '1',
      phone: registerForm.phone,
      username: registerForm.username,
      avatar: ''
    })

    ElMessage.success('注册成功！')

    router.replace('/dashboard')
  } catch (error: any) {
    ElMessage.error(error.message || '注册失败，请重试')
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
  background: var(--bg-page);
  position: relative;
  overflow: hidden;
}

.background {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  width: 100%;
  height: 100%;
  background-image:
    linear-gradient(rgba(34, 197, 94, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 197, 94, 0.03) 1px, transparent 1px);
  background-size: 50px 50px;
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
}

.bg-glow-1 {
  width: 600px;
  height: 600px;
  background: rgba(34, 197, 94, 0.15);
  top: -200px;
  right: -200px;
}

.bg-glow-2 {
  width: 500px;
  height: 500px;
  background: rgba(34, 197, 94, 0.1);
  bottom: -200px;
  left: -200px;
}

.container {
  display: flex;
  width: 1000px;
  max-width: 95vw;
  height: 680px;
  max-height: 95vh;
  background-color: var(--bg-card);
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  position: relative;
  z-index: 1;
  border: 1px solid var(--border-color);
}

@media (max-width: 768px) {
  .container {
    flex-direction: column;
    width: 95vw;
    max-width: 100%;
    height: auto;
    min-height: 100vh;
    border-radius: 0;
  }
  
  .brand-section {
    width: 100%;
    padding: 32px 24px;
    min-height: auto;
  }
  
  .form-section {
    width: 100%;
    padding: 32px 24px;
    flex: 1;
  }
}

.brand-section {
  width: 40%;
  padding: 48px 40px;
  background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
  color: white;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.brand-section::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, transparent 50%),
    linear-gradient(225deg, rgba(34, 197, 94, 0.05) 0%, transparent 50%);
}

.brand-logo {
  width: 72px;
  height: 72px;
  border-radius: 20px;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  position: relative;
  z-index: 1;
  box-shadow: 0 8px 24px rgba(34, 197, 94, 0.3);
}

.brand-section h1 {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  position: relative;
  z-index: 1;
}

.brand-section p {
  margin: 0 0 32px 0;
  opacity: 0.8;
  font-size: 14px;
  position: relative;
  z-index: 1;
}

.features {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
}

.feature-item svg {
  color: var(--primary-color);
}

.form-section {
  width: 60%;
  padding: 48px 48px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  max-height: 100%;
}

.tabs {
  display: flex;
  margin-bottom: 32px;
  gap: 8px;
}

.tab-btn {
  flex: 1;
  padding: 12px;
  border: none;
  background-color: transparent;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 8px;
}

.tab-btn.active {
  color: var(--primary-color);
  background: var(--primary-bg);
}

.login-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  padding: 4px;
  background: var(--card-bg);
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.login-tab {
  flex: 1;
  padding: 10px;
  border: none;
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s;
}

.login-tab.active {
  background: var(--gradient-primary);
  color: white;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.25);
}

.form h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.form-desc {
  margin: 0 0 24px 0;
  color: var(--text-secondary);
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

.form :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 0 16px;
}

.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 20px;
  font-size: 13px;
  color: var(--text-secondary);
  /* cursor: pointer; */
}

.checkbox-label input {
  width: 0;
  /* height: 16px; */
  accent-color: var(--primary-color);
}
.checkbox-text {
  min-width: 300px;
  font-size: 13px;
}

.forgot-link {
  font-size: 13px;
  color: var(--primary-color);
  text-decoration: none;
  transition: color 0.2s;
}

.forgot-link:hover {
  color: var(--primary-light);
}

.submit-btn {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
  background: var(--gradient-primary);
  border: none;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.25);
  transition: all 0.2s ease;
}

.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.35);
}

.captcha-input-wrapper {
  display: flex;
  gap: 12px;
}

.captcha-input-wrapper :deep(.el-form-item) {
  margin-bottom: 0;
}

.captcha-input-wrapper :deep(.el-input) {
  flex: 1;
  height: 44px;
}

.captcha-input-wrapper :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 0 16px;
}

.captcha-image-wrapper {
  position: relative;
  width: 120px;
  height: 44px;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.captcha-image-wrapper:hover {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-bg);
}

.captcha-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.captcha-loading {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.captcha-loading .loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.captcha-refresh-hint {
  position: absolute;
  bottom: 2px;
  right: 4px;
  font-size: 10px;
  color: var(--text-placeholder);
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 4px;
  border-radius: 4px;
}

.captcha-btn {
  padding: 0 12px;
  height: 28px;
  font-size: 13px;
  color: var(--primary-color);
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
  font-weight: 500;
}

.captcha-btn:hover:not(:disabled) {
  background: var(--primary-bg);
}

.captcha-btn:disabled {
  color: var(--text-placeholder);
  cursor: not-allowed;
}

.terms {
  margin-bottom: 24px;
}

.terms a {
  color: var(--primary-color);
  text-decoration: none;
  transition: color 0.2s;
}

.terms a:hover {
  color: var(--primary-light);
  text-decoration: underline;
}
</style>
