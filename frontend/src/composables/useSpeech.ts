/**
 * 朗读（TTS）播放器 —— 基于浏览器原生 Web Speech API。
 *
 * 设计要点：
 * 1. **模块级单例状态**：同一时刻全局只允许一条消息在朗读。所有组件共享
 *    同一个 `activeId`，因此点第二条会自动打断第一条，不需要组件间通信。
 * 2. **分块排队**：Chrome 对单条 utterance 有约 15 秒静默截断缺陷，长回答
 *    必须切块后用 onend 串联播放（见 speech-text.ts）。
 * 3. **不支持即静默降级**：`supported` 为 false 时组件隐藏按钮，不报错。
 */

import { computed, ref } from 'vue'
import {
  detectSpeechLang,
  pickVoice,
  prepareSpeechText,
  splitSpeechChunks,
} from '@/utils/speech-text'

/** 全局播放状态：'idle' 空闲 | 'playing' 朗读中 | 'paused' 已暂停 */
export type SpeechStatus = 'idle' | 'playing' | 'paused'

const status = ref<SpeechStatus>('idle')
/** 正在朗读/暂停的消息 id；null 表示无 */
const activeId = ref<string | null>(null)

/** 当前消息切好的块、播放进度，以及整条消息的语种 */
let chunks: string[] = []
let chunkIndex = 0
let chunkLang: 'zh-CN' | 'en-US' = 'zh-CN'

/**
 * 播放代际令牌。每次 speak/stop 都自增。
 *
 * 旧 utterance 的回调是异步派发的：切换消息后，上一条的 onend 仍可能在新的
 * 播放开始之后才到达。只靠 `activeId === null` 判断挡不住这种情况（此时
 * activeId 已是新消息的 id），旧回调会错误地推进**新**消息的 chunkIndex，
 * 导致新回答被跳过一整块。回调里校验令牌即可让陈旧回调全部失效。
 */
let playToken = 0

/** 引擎是否可用。SSR / 老浏览器 / jsdom 测试环境下为 false */
const supported =
  typeof window !== 'undefined' &&
  typeof window.speechSynthesis !== 'undefined' &&
  typeof window.SpeechSynthesisUtterance !== 'undefined'

/** 音色列表在部分浏览器是异步填充的，首次可能为空，需要等 voiceschanged */
let cachedVoices: SpeechSynthesisVoice[] = []
const refreshVoices = () => {
  if (!supported) return
  const list = window.speechSynthesis.getVoices()
  if (list.length) cachedVoices = list
}

if (supported) {
  refreshVoices()
  // 音色列表异步就绪后回填；用 addEventListener 而非 onvoiceschanged 避免覆盖他人
  window.speechSynthesis.addEventListener?.('voiceschanged', refreshVoices)
}

/** 清空队列并停止发声。注意 cancel() 会触发未播完 utterance 的 onerror(interrupted) */
const teardown = () => {
  // 令牌自增，令所有在途的 onend/onerror 回调失效
  playToken += 1
  chunks = []
  chunkIndex = 0
  activeId.value = null
  status.value = 'idle'
}

/** 朗读下一块；播完自动续下一块，全部播完则归零 */
const speakChunk = () => {
  if (!supported) return
  const text = chunks[chunkIndex]
  if (text === undefined) {
    teardown()
    return
  }

  const token = playToken
  const utterance = new SpeechSynthesisUtterance(text)
  // 用整条消息的语种，而不是每块各自判定：中英混排的长回答若逐块判定，
  // 音色会在中文块和英文块之间来回跳，听起来像换了个人在念。
  utterance.lang = chunkLang
  const voice = pickVoice(cachedVoices, chunkLang)
  if (voice) utterance.voice = voice

  utterance.onend = () => {
    // 令牌不匹配 = 这条已被打断/替换，回调属于上一轮播放，直接丢弃
    if (token !== playToken) return
    chunkIndex += 1
    speakChunk()
  }
  utterance.onerror = (event) => {
    if (token !== playToken) return
    // interrupted/canceled 是主动取消的正常结果，不算失败
    const reason = (event as SpeechSynthesisErrorEvent).error
    if (reason === 'interrupted' || reason === 'canceled') return
    console.warn('[speech] 朗读失败:', reason)
    window.speechSynthesis.cancel()
    teardown()
  }

  window.speechSynthesis.speak(utterance)
}

/**
 * 朗读一条消息。点另一条时会取消当前这条，全局始终只有一条在念。
 */
export function speak(id: string, rawText: string): void {
  if (!supported) return

  const prepared = prepareSpeechText(rawText)
  const nextChunks = splitSpeechChunks(prepared)
  if (!nextChunks.length) return

  // 先作废旧一轮（自增令牌并清 activeId），再启动新一轮
  window.speechSynthesis.cancel()
  playToken += 1
  activeId.value = null

  refreshVoices()
  chunks = nextChunks
  chunkIndex = 0
  chunkLang = detectSpeechLang(prepared)
  activeId.value = id
  status.value = 'playing'
  speakChunk()
}

/** 停止朗读并清空状态（可被任意组件调用，幂等） */
export function stop(): void {
  if (!supported) return
  window.speechSynthesis.cancel()
  teardown()
}

/** 暂停当前朗读 */
export function pause(): void {
  if (!supported || status.value !== 'playing') return
  window.speechSynthesis.pause()
  status.value = 'paused'
}

/** 恢复暂停的朗读 */
export function resume(): void {
  if (!supported || status.value !== 'paused') return
  window.speechSynthesis.resume()
  status.value = 'playing'
}

/**
 * 朗读开关：点同一条在播 → 暂停/恢复，点另一条 → 切换过去。
 * 组件只需要调这一个函数。
 */
export function toggle(id: string, rawText: string): void {
  if (!supported) return
  if (activeId.value === id) {
    if (status.value === 'playing') pause()
    else if (status.value === 'paused') resume()
    return
  }
  speak(id, rawText)
}

/** 共享的只读播放状态，供组件判断「我这条是否在朗读」 */
export function useSpeech() {
  return {
    supported,
    status,
    activeId,
    isActive: (id: string) => activeId.value === id,
    isPlaying: (id: string) => activeId.value === id && status.value === 'playing',
    isPaused: (id: string) => activeId.value === id && status.value === 'paused',
    anyActive: computed(() => activeId.value !== null),
    speak,
    stop,
    pause,
    resume,
    toggle,
  }
}

/** 测试用：重置模块级单例状态，避免用例间互相污染 */
export function __resetSpeechForTests(): void {
  playToken += 1
  chunks = []
  chunkIndex = 0
  chunkLang = 'zh-CN'
  activeId.value = null
  status.value = 'idle'
  cachedVoices = []
}
