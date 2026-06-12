import api from '@/utils/request'
import type { Resource } from './types'

/**
 * 生成资源（SSE流式）
 * @param topic - 主题
 */
export const generateResource = (topic: string): Promise<Response> => {
  return fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/resources/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify({ topic })
  })
}

/**
 * 获取我的资源列表
 */
export const getMyResources = (): Promise<Resource[]> => {
  return api.get('/api/resources/list')
}

/**
 * 按类型筛选资源
 * @param type - 资源类型
 */
export const getResourcesByType = (type: 'course_doc' | 'mind_map' | 'exercise' | 'reading' | 'code_practice'): Promise<Resource[]> => {
  return api.get(`/api/resources/list/${type}`)
}

/**
 * 获取资源详情
 * @param resourceId - 资源ID
 */
export const getResourceDetail = (resourceId: number): Promise<Resource> => {
  return api.get(`/api/resources/${resourceId}`)
}

/**
 * 删除资源
 * @param resourceId - 资源ID
 */
export const deleteResource = (resourceId: number): Promise<void> => {
  return api.delete(`/api/resources/${resourceId}`)
}

/**
 * 导出PPTX
 * @param data - 导出数据
 */
export const exportPPTX = (data: {
  title: string
  content_blocks: Array<{
    type: 'title' | 'text' | 'code'
    text: string
    level?: number
    language?: string
  }>
}): Promise<Blob> => {
  return api.post('/api/resources/export-pptx', data, {
    responseType: 'blob'
  })
}
