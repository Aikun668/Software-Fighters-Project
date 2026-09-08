  import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
/**
 * 创建 axios 实例
 */
const createInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 10000,
    headers: {
      'token': localStorage.getItem('token') || ''
    }
  })

  return instance
}

const request = createInstance()

/**
 * 请求拦截器
 */
request.interceptors.request.use(
  // @ts-ignore
    (config: AxiosRequestConfig) => {
    // 从 localStorage 读取 token
    const token = localStorage.getItem('token')
    
    // 添加 token 到请求头
    if (token) {
      config.headers = config.headers || {}
      config.headers['Authorization'] = `Bearer ${token}`
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器
 */
request.interceptors.response.use(
  (response: AxiosResponse) => {
    const { data } = response

    // 统一处理响应格式
    if (data.code === 0 || data.success) {
      return data.data || data
    } else {
      ElMessage.error(data.message || '请求失败')
      return Promise.reject(data)
    }
  },
  (error) => {
    const { response } = error

    if (response) {
      // HTTP 状态码错误
      switch (response.status) {
        case 401:
          ElMessage.error('登录已过期，请重新登录')
          const userStore = useUserStore()
          userStore.logout()
          // 跳转到登录页
          if (typeof window !== 'undefined') {
            window.location.href = '/loginRegister'
          }
          break
        case 403:
          ElMessage.error('暂无权限访问')
          break
        case 404:
          ElMessage.error('接口不存在')
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(response.data?.message || '请求失败')
      }
    } else {
      ElMessage.error('网络异常，请稍后重试')
    }

    return Promise.reject(error)
  }
)

/**
 * 请求方法封装
 */
const api = {
  get<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<T> {
    return request.get(url, { params, ...config })
  },

  post<T = any>(url: string, data?: Record<string, any>, config?: AxiosRequestConfig): Promise<T> {
    return request.post(url, data, config)
  },

  put<T = any>(url: string, data?: Record<string, any>, config?: AxiosRequestConfig): Promise<T> {
    return request.put(url, data, config)
  },

  delete<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<T> {
    return request.delete(url, { params, ...config })
  },

  patch<T = any>(url: string, data?: Record<string, any>, config?: AxiosRequestConfig): Promise<T> {
    return request.patch(url, data, config)
  }
}

export default api
export { request }
