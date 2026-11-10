/**
 * 复制文本到剪贴板（含降级路径）。
 *
 * 为什么不用一行 `navigator.clipboard.writeText`：
 * 1. **安全上下文限制**：`navigator.clipboard` 只在 https / localhost 下存在。
 *    项目用 `http://<局域网IP>:5173` 给学生机演示时它是 undefined，一行写法会直接
 *    抛 TypeError，按钮点了没反应。
 * 2. **权限拒绝**：即使 API 存在，浏览器也可能因权限策略 reject。用户看到的结果
 *    应该是「复制失败」而不是控制台一片红。
 * 3. 因此统一收敛成布尔返回值：调用方只管展示成功/失败，不处理异常。
 */

/**
 * 老式降级方案：临时 textarea + document.execCommand('copy')。
 *
 * 该 API 已废弃但在桌面 Chrome/Edge/Firefox 上仍可用，是局域网 http 场景下
 * 唯一能用的路径。返回是否复制成功；环境完全不支持时返回 false。
 */
const copyByExecCommand = (text: string): boolean => {
  if (typeof document === 'undefined') return false
  // jsdom / 部分精简环境没有实现 execCommand，调用会抛错，先探测
  if (typeof document.execCommand !== 'function') return false

  const textarea = document.createElement('textarea')
  textarea.value = text
  // 只读 + aria-hidden，避免被读屏软件念出这段临时文本
  textarea.setAttribute('readonly', '')
  textarea.setAttribute('aria-hidden', 'true')
  /**
   * 必须留在视口内才能被选中：`display: none` / `visibility: hidden` 的元素
   * 无法参与选区，execCommand 会失败。用固定定位 + 透明移出可视区即可。
   */
  textarea.style.position = 'fixed'
  textarea.style.top = '-9999px'
  textarea.style.left = '-9999px'
  textarea.style.opacity = '0'

  document.body.appendChild(textarea)
  try {
    textarea.select()
    // iOS Safari 需要显式 setSelectionRange 才认这段选区
    textarea.setSelectionRange(0, textarea.value.length)
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    // 无论成败都要摘掉临时节点，否则每次复制都在 body 里堆一个 textarea
    textarea.remove()
  }
}

/**
 * 把文本写入剪贴板。**不会抛异常**，只返回是否成功。
 *
 * @param text 待复制文本（消息场景下传原始 Markdown 正文）
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒 / 非聚焦文档等：继续尝试降级方案，而不是直接判失败
    }
  }
  return copyByExecCommand(text)
}
