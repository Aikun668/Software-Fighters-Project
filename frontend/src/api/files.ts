import api from '@/utils/request'
import type { FileUploadResponse } from './types'

/**
 * 上传文件
 * @param file - 文件对象
 */
export const uploadFile = (file: File): Promise<FileUploadResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  
  return api.post('/api/file/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 获取文件访问URL
 * @param fileId - 文件ID
 */
export const getFileUrl = (fileId: number): Promise<string> => {
  return api.get(`/api/file/url/${fileId}`)
}

/**
 * 删除文件
 * @param fileId - 文件ID
 */
export const deleteFile = (fileId: number): Promise<void> => {
  return api.delete(`/api/file/${fileId}`)
}
