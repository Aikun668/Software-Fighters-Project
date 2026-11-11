<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ArrowUp, BookOpen, ChevronDown, FileText, Paperclip, Sparkles, X } from '@lucide/vue'
import type { ChatAttachment, ChatMode, ChatStyle } from './chat-types'

const props = defineProps<{
  prompt: string
  resourceMode: boolean
  selectedModeLabel: string
  selectedStyleLabel: string
  modeOptions: Array<{ value: ChatMode; label: string }>
  styleOptions: Array<{ value: ChatStyle; label: string }>
  attachments: ChatAttachment[]
  uploadError: string
  uploadingFile: boolean
  sending: boolean
}>()

const emit = defineEmits<{
  'update:prompt': [value: string]
  send: []
  stop: []
  chooseMode: [mode: ChatMode]
  chooseStyle: [style: ChatStyle]
  removeAttachment: [fileId: number]
  uploadFiles: [files: File[]]
}>()

const promptInput = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const modeMenuOpen = ref(false)
const styleMenuOpen = ref(false)
const dragActive = ref(false)

const toggleModeMenu = () => {
  modeMenuOpen.value = !modeMenuOpen.value
  styleMenuOpen.value = false
}

const toggleStyleMenu = () => {
  styleMenuOpen.value = !styleMenuOpen.value
  modeMenuOpen.value = false
}

const chooseMode = (mode: ChatMode) => {
  emit('chooseMode', mode)
  modeMenuOpen.value = false
}

const chooseStyle = (style: ChatStyle) => {
  emit('chooseStyle', style)
  styleMenuOpen.value = false
}

const openFilePicker = () => {
  fileInput.value?.click()
}

/** 部分来源（另存/拖拽）不带 MIME，按扩展名补一个，避免图片被错判为非图片 */
const MIME_BY_EXTENSION: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
  bmp: 'image/bmp',
}

const withInferredMime = (file: File): File => {
  if (file.type) return file
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  const mime = MIME_BY_EXTENSION[ext]
  if (!mime) return file
  // File#type 只读，只能按同样的内容重建一个带类型的新 File
  return new File([file], file.name, { type: mime, lastModified: file.lastModified })
}

/** 补全图片 MIME。非图片会在上传前被拒绝，避免看起来发出去了却没被阅读。 */
const pickFiles = (files: Iterable<File> | null | undefined): File[] =>
  Array.from(files ?? []).map(withInferredMime)

/**
 * 从剪贴板取文件。
 * Chrome/Edge 会填 clipboardData.files，Safari 等只填 items，
 * 两条路径都走一遍并按 (name,size,type) 去重，避免同一份文件上传两次。
 */
const filesFromClipboard = (data: DataTransfer | null | undefined): File[] => {
  if (!data) return []
  const fromItems = Array.from(data.items ?? [])
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)

  const merged = [...pickFiles(data.files), ...pickFiles(fromItems)]
  const seen = new Set<string>()
  return merged.filter((file) => {
    const key = `${file.name}|${file.size}|${file.type}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

const submitFiles = (files: File[]) => {
  if (files.length) emit('uploadFiles', files)
}

const handleFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = pickFiles(input.files)
  // 先清空 input，保证同一文件连续选择两次也能再次触发 change
  input.value = ''
  submitFiles(files)
}

/**
 * 粘贴上传：剪贴板里的文件（截图、复制的文件）直接进附件条。
 * 截图工具写入剪贴板的条目常常只有 blob 没有文件名，
 * 这里不依赖 name，一律交给后端按 MIME 补后缀。
 * 粘贴纯文本时没有任何文件，不拦截默认行为。
 */
const handlePaste = (event: ClipboardEvent) => {
  const files = filesFromClipboard(event.clipboardData)
  if (!files.length) return
  event.preventDefault()
  submitFiles(files)
}

const handleDrop = (event: DragEvent) => {
  dragActive.value = false
  const files = pickFiles(event.dataTransfer?.files)
  if (!files.length) return
  event.preventDefault()
  submitFiles(files)
}

const resizePrompt = () => {
  const textarea = promptInput.value
  if (!textarea) return

  textarea.style.height = 'auto'
  const maxHeight = 180
  const nextHeight = Math.min(Math.max(textarea.scrollHeight, 58), maxHeight)
  textarea.style.height = `${nextHeight}px`
  textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
}

watch(() => props.prompt, () => {
  void nextTick().then(resizePrompt)
})
</script>

<template>
  <div
    class="composer"
    :class="{ 'drag-active': dragActive }"
    @dragover.prevent="dragActive = true"
    @dragleave="dragActive = false"
    @drop="handleDrop"
  >
    <div v-if="attachments.length" class="attachment-list">
      <span v-for="attachment in attachments" :key="attachment.fileId" class="attachment-chip">
        <img v-if="attachment.isImage" class="attachment-thumb" :src="attachment.url" :alt="attachment.name" />
        <FileText v-else class="attachment-icon" :size="18" :stroke-width="1.4" />
        <span class="attachment-name">{{ attachment.name }}</span>
        <button type="button" aria-label="移除附件" @click="emit('removeAttachment', attachment.fileId)"><X :size="13" :stroke-width="1.8" /></button>
      </span>
    </div>
    <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>
    <input ref="fileInput" class="file-input" type="file" accept="image/*" multiple @change="handleFileChange" />
    <textarea
      ref="promptInput"
      :value="prompt"
      rows="1"
      :placeholder="resourceMode ? '输入主题，我生成学习资料...' : '向我提问，或粘贴图片/学习内容...'"
      @input="emit('update:prompt', ($event.target as HTMLTextAreaElement).value)"
      @paste="handlePaste"
      @keydown.enter.exact.prevent="emit('send')"
    />
    <div class="composer-toolbar">
      <div class="toolbar-menu-wrap">
        <button type="button" class="toolbar-select" @click="toggleModeMenu"><Sparkles :size="16" :stroke-width="1.45" />{{ selectedModeLabel }} <ChevronDown :size="14" /></button>
        <div v-if="modeMenuOpen" class="toolbar-menu" role="menu">
          <button v-for="option in modeOptions" :key="option.value" type="button" :data-mode="option.value" @click="chooseMode(option.value)">{{ option.label }}</button>
        </div>
      </div>
      <button type="button" :disabled="uploadingFile" @click="openFilePicker"><Paperclip :size="17" :stroke-width="1.45" />{{ uploadingFile ? '上传中' : '附件' }}</button>
      <div class="toolbar-menu-wrap">
        <button type="button" data-style-trigger @click="toggleStyleMenu"><BookOpen :size="17" :stroke-width="1.45" />{{ selectedStyleLabel }} <ChevronDown :size="14" /></button>
        <div v-if="styleMenuOpen" class="toolbar-menu" role="menu">
          <button v-for="option in styleOptions" :key="option.value" type="button" :data-style="option.value" @click="chooseStyle(option.value)">{{ option.label }}</button>
        </div>
      </div>
      <button v-if="sending" type="button" class="send-button stop-button" aria-label="停止" @click="emit('stop')">停</button>
      <button v-else type="button" class="send-button" aria-label="发送" :disabled="uploadingFile" @click="emit('send')"><ArrowUp :size="20" :stroke-width="1.6" /></button>
    </div>
  </div>
</template>

<style scoped>
.composer { position: relative; overflow: visible; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,254,250,.88); box-shadow: 0 10px 28px rgba(122,105,82,.08); }
.composer.drag-active { border-color: var(--clay); box-shadow: 0 0 0 3px rgba(191,136,110,.18); }
.composer textarea { display: block; width: 100%; height: 58px; min-height: 58px; max-height: 180px; padding: 14px 18px; resize: none; border: 0; outline: 0; overflow-y: hidden; background: transparent; color: var(--ink); font-size: 15px; line-height: 1.55; }
.composer textarea::placeholder { color: var(--soft-muted); }
.composer-toolbar { display: flex; align-items: center; gap: 20px; min-height: 50px; padding: 0 15px 0 17px; border-top: 1px solid var(--line); }
.composer-toolbar button { display: inline-flex; align-items: center; gap: 7px; border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; }
.composer-toolbar button:hover { color: var(--ink); }
.toolbar-select { padding-right: 14px !important; border-right: 1px solid var(--line) !important; }
.send-button { justify-content: center; width: 38px; height: 38px; margin-left: auto; border-radius: 50% !important; background: var(--clay) !important; color: #fffaf6 !important; }
.send-button:hover { background: #b97c65 !important; }
.send-button:disabled { opacity: .55; cursor: not-allowed; }
.file-input { display: none; }
.attachment-list { display: flex; flex-wrap: wrap; gap: 7px; padding: 10px 18px 0; }
.attachment-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 5px 8px 5px 5px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface-muted); color: var(--muted); font-size: 12px; }
.attachment-thumb { width: 26px; height: 26px; flex: 0 0 auto; border-radius: 6px; object-fit: cover; background: var(--line); }
.attachment-icon { flex: 0 0 auto; color: var(--muted); }
.attachment-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attachment-chip button { display: inline-flex; align-items: center; justify-content: center; width: 17px; height: 17px; flex: 0 0 auto; padding: 0; border: 0; background: transparent; color: var(--muted); cursor: pointer; }
.attachment-chip button:hover { color: var(--ink); }
.upload-error { margin: 8px 18px 0; color: #b4483c; font-size: 12px; }
.toolbar-menu-wrap { position: relative; }
.toolbar-menu { position: absolute; bottom: calc(100% + 9px); left: -7px; z-index: 4; display: grid; min-width: 118px; gap: 3px; padding: 6px; border: 1px solid var(--line); border-radius: 9px; background: var(--page); box-shadow: 0 10px 25px rgba(70,58,43,.14); }
.toolbar-menu button { justify-content: flex-start; width: 100%; padding: 8px 9px; border-radius: 6px; color: var(--muted); white-space: nowrap; }
.toolbar-menu button:hover { background: var(--sage-soft); color: var(--ink); }
@media (max-width: 620px) { .composer-toolbar { gap: 12px; padding-left: 13px; }.composer-toolbar button { font-size: 12px; }.composer-toolbar button:nth-child(2), .composer-toolbar button:nth-child(3) { display: none; } }
</style>

