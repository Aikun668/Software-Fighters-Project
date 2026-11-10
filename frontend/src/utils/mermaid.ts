/**
 * Mermaid 渲染（FINAL 用户需求：AI 返回的 mindmap/流程图代码块渲染不出来）。
 *
 * 背景：AI 正文里的 ```mermaid 代码块（mindmap / flowchart / sequenceDiagram…）
 * 此前只是普通代码块。这里在 Markdown 渲染进 DOM 后，把这些代码块替换成 SVG 图。
 *
 * 设计要点：
 * - **懒加载**：mermaid 体积大（~1MB），只在页面首次出现 mermaid 块时才动态 import；
 * - **按 id 渲染**：mermaid.render 需要一个唯一 id，失败时保留原代码块并标注错误；
 * - **流式友好**：渲染是幂等的（已渲染的块带 data-mermaid-done 标记，跳过），
 *   流式输出期间每个 token 都会触发全量 Markdown 重渲染，但只有新出现的块会走渲染。
 * - DOMPurify 已在 Markdown 层清洗过正文；SVG 由 mermaid 生成（内部 escape 自身输入）。
 */

let mermaidModule: Promise<typeof import('mermaid')['default']> | null = null
let renderSeq = 0

const loadMermaid = async () => {
  if (!mermaidModule) {
    mermaidModule = import('mermaid').then((mod) => {
      const mermaid = mod.default
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'neutral',
        fontFamily: 'inherit',
        mindmap: { padding: 12 },
      })
      return mermaid
    })
  }
  return mermaidModule
}

/** 是否为 mermaid 图类型（覆盖常用几种，未识别的交给 mermaid 自己报错） */
const isMermaidCode = (code: string): boolean =>
  /^\s*(mindmap|flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|timeline|mindmap|gitGraph|quadrantChart|zenuml|sankey|block-beta)\b/i.test(
    code,
  )

/**
 * 扫描容器内所有未渲染的 mermaid 代码块并替换为 SVG。
 * 幂等：已带 data-mermaid-done 的块跳过。
 */
export const renderMermaidBlocks = async (container: HTMLElement | null | undefined): Promise<void> => {
  if (!container) return
  const blocks = container.querySelectorAll<HTMLElement>(
    'pre code.language-mermaid:not([data-mermaid-done])',
  )
  if (!blocks.length) return

  // 只要有块要渲染才加载 mermaid（避免无关页面加载 1MB 依赖）
  let mermaid: Awaited<ReturnType<typeof loadMermaid>> | null = null
  try {
    mermaid = await loadMermaid()
  } catch (error) {
    console.error('[mermaid] 加载失败', error)
    return
  }

  for (const block of blocks) {
    const code = block.textContent ?? ''
    const pre = block.closest('pre')
    if (!pre || !code.trim() || !isMermaidCode(code)) {
      // 不是合法图类型的代码块：标记跳过，避免每轮 watch 重复扫描
      block.dataset.mermaidDone = 'true'
      continue
    }

    // 每个块独立 try/catch：一个块语法错误（或流式中途残缺）不得拖垮其余块，
    // 也不得把异常抛回 watch 造成 unhandled rejection。
    try {
      const holder = document.createElement('div')
      holder.className = 'mermaid-figure'
      renderSeq += 1
      const { svg, bindFunctions } = await mermaid.render(`mermaid-svg-${renderSeq}`, code)
      holder.innerHTML = svg
      pre.replaceWith(holder)
      try {
        await bindFunctions?.(holder)
      } catch {
        // 绑定交互失败不影响展示
      }
      // 只有渲染成功才标记：失败块保留原代码块，等下一轮（流结束后）重试
      block.dataset.mermaidDone = 'true'
    } catch (error) {
      console.warn('[mermaid] 渲染失败，暂保留代码块，流结束后重试:', error)
      // 不标记 done：流式期间语法不完整会失败，结束后下一轮 watch 会重试
    }
  }
}
