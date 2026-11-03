import api from '@/utils/request'
import type { FileUploadResponse } from './types'

/** 附件上传超时：全局默认 10s 对 20MB 图片偏紧，慢网络下会误判为失败 */
const UPLOAD_TIMEOUT_MS = 60_000

/**
 * 上传文件
 *
 * 不手写 `Content-Type: multipart/form-data`：该值必须带浏览器生成的
 * `boundary=...`，缺 boundary 会让后端 multipart 解析直接失败。
 * axios 目前会替 FormData 剥掉这个头（fetch 适配器里也是显式删除），
 * 但这是适配器内部行为，交给浏览器自动设置才是稳的。
 * @param file - 文件对象
 */
export const uploadFile = (file: File): Promise<FileUploadResponse> => {
  const formData = new FormData()
  formData.append('file', file)

  return api.post('/file/upload', formData, { timeout: UPLOAD_TIMEOUT_MS })
}

/**
 * 获取文件访问URL
 * @param fileId - 文件ID
 */
export const getFileUrl = (fileId: number): Promise<string> => {
  return api.get(`/file/url/${fileId}`)
}

/**
 * 删除文件
 * @param fileId - 文件ID
 */
export const deleteFile = (fileId: number): Promise<void> => {
  return api.delete(`/file/${fileId}`)
}
