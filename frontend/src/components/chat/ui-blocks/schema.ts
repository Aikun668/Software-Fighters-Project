/**
 * 结构化 UI block 的 schema 校验（手写类型守卫，不引入第三方库）。
 *
 * block 形如 `{ type, version, props }`。AI 输出的 props 不得包含 `weights`（D-007）。
 */

export const ATTENTION_MODES = ['causal', 'bidirectional'] as const
export type AttentionMode = (typeof ATTENTION_MODES)[number]

export const ATTENTION_TOKEN_MIN = 3
export const ATTENTION_TOKEN_MAX = 8

export interface AttentionMatrixProps {
  tokenCount: number
  mode: AttentionMode
  queryLabels?: string[]
  keyLabels?: string[]
}

// conv_window v1：网格 + 卷积核滑窗（CNN/卷积/特征图/感受野）
export const CONV_ROWS_MIN = 3
export const CONV_ROWS_MAX = 8
export const CONV_COLS_MIN = 3
export const CONV_COLS_MAX = 8
export const CONV_KERNEL_MIN = 2
export const CONV_KERNEL_MAX = 5
export const CONV_STRIDE_MIN = 1
export const CONV_STRIDE_MAX = 2

/** stride 未提供时规范化为默认值 1（校验通过后 props 恒携带 stride） */
export interface ConvWindowProps {
  inputRows: number
  inputCols: number
  kernelSize: number
  stride: number
}

export interface UiBlockEnvelope {
  type: string
  version: number
  props: unknown
}

export type ValidationResult<T> = { ok: true; value: T } | { ok: false; error: string }

const ENVELOPE_KEYS = ['type', 'version', 'props'] as const
const ATTENTION_PROP_KEYS = ['tokenCount', 'mode', 'queryLabels', 'keyLabels'] as const
const CONV_PROP_KEYS = ['inputRows', 'inputCols', 'kernelSize', 'stride'] as const

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isAttentionMode = (value: unknown): value is AttentionMode =>
  ATTENTION_MODES.some((mode) => mode === value)

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string')

const findUnknownKey = (obj: Record<string, unknown>, allowed: readonly string[]) =>
  Object.keys(obj).find((key) => !allowed.includes(key))

/** 校验外层结构 `{ type, version, props }`，不检查 type 是否已注册。 */
export const parseUiBlockEnvelope = (input: unknown): ValidationResult<UiBlockEnvelope> => {
  if (!isPlainObject(input)) return { ok: false, error: 'UI block 必须是对象' }

  const unknownKey = findUnknownKey(input, ENVELOPE_KEYS)
  if (unknownKey !== undefined) {
    return { ok: false, error: `UI block 含有未知字段 "${unknownKey}"` }
  }

  const { type, version } = input
  if (typeof type !== 'string' || type.length === 0) {
    return { ok: false, error: 'type 必须是非空字符串' }
  }
  if (typeof version !== 'number' || !Number.isInteger(version)) {
    return { ok: false, error: `version 必须是整数，当前为 ${JSON.stringify(version)}` }
  }
  if (!('props' in input)) return { ok: false, error: '缺少 props' }

  return { ok: true, value: { type, version, props: input.props } }
}

const parseLabels = (
  name: string,
  value: unknown,
  tokenCount: number,
): ValidationResult<string[] | undefined> => {
  if (value === undefined) return { ok: true, value: undefined }
  if (!isStringArray(value)) return { ok: false, error: `${name} 必须是字符串数组` }
  if (value.length !== tokenCount) {
    return {
      ok: false,
      error: `${name} 长度必须等于 tokenCount (${tokenCount})，当前为 ${value.length}`,
    }
  }
  return { ok: true, value: [...value] }
}

const isIntInRange = (value: unknown, min: number, max: number): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max

/** 校验 attention_matrix v1 的 props，并返回规范化后的副本。 */
export const validateAttentionMatrixProps = (
  input: unknown,
): ValidationResult<AttentionMatrixProps> => {
  if (!isPlainObject(input)) {
    return { ok: false, error: 'attention_matrix 的 props 必须是对象' }
  }
  if ('weights' in input) {
    return {
      ok: false,
      error: 'props 不允许包含 weights：AI 输出不得提供真实注意力权重（D-007）',
    }
  }
  const unknownKey = findUnknownKey(input, ATTENTION_PROP_KEYS)
  if (unknownKey !== undefined) {
    return { ok: false, error: `props 含有未知字段 "${unknownKey}"` }
  }

  const { tokenCount, mode } = input
  if (
    typeof tokenCount !== 'number' ||
    !Number.isInteger(tokenCount) ||
    tokenCount < ATTENTION_TOKEN_MIN ||
    tokenCount > ATTENTION_TOKEN_MAX
  ) {
    return {
      ok: false,
      error: `tokenCount 必须是 ${ATTENTION_TOKEN_MIN}..${ATTENTION_TOKEN_MAX} 之间的整数，当前为 ${JSON.stringify(tokenCount)}`,
    }
  }
  if (!isAttentionMode(mode)) {
    return {
      ok: false,
      error: `mode 必须是 causal 或 bidirectional，当前为 ${JSON.stringify(mode)}`,
    }
  }

  const queryLabels = parseLabels('queryLabels', input.queryLabels, tokenCount)
  if (!queryLabels.ok) return queryLabels
  const keyLabels = parseLabels('keyLabels', input.keyLabels, tokenCount)
  if (!keyLabels.ok) return keyLabels

  return {
    ok: true,
    value: {
      tokenCount,
      mode,
      ...(queryLabels.value && { queryLabels: queryLabels.value }),
      ...(keyLabels.value && { keyLabels: keyLabels.value }),
    },
  }
}

/** 校验 conv_window v1 的 props（镜像后端 _parse_conv_props），返回规范化副本（stride 默认 1）。 */
export const validateConvWindowProps = (
  input: unknown,
): ValidationResult<ConvWindowProps> => {
  if (!isPlainObject(input)) {
    return { ok: false, error: 'conv_window 的 props 必须是对象' }
  }
  const unknownKey = findUnknownKey(input, CONV_PROP_KEYS)
  if (unknownKey !== undefined) {
    return { ok: false, error: `props 含有未知字段 "${unknownKey}"` }
  }

  const { inputRows, inputCols, kernelSize, stride } = input
  if (!isIntInRange(inputRows, CONV_ROWS_MIN, CONV_ROWS_MAX)) {
    return {
      ok: false,
      error: `inputRows 必须是 ${CONV_ROWS_MIN}..${CONV_ROWS_MAX} 之间的整数，当前为 ${JSON.stringify(inputRows)}`,
    }
  }
  if (!isIntInRange(inputCols, CONV_COLS_MIN, CONV_COLS_MAX)) {
    return {
      ok: false,
      error: `inputCols 必须是 ${CONV_COLS_MIN}..${CONV_COLS_MAX} 之间的整数，当前为 ${JSON.stringify(inputCols)}`,
    }
  }
  if (!isIntInRange(kernelSize, CONV_KERNEL_MIN, CONV_KERNEL_MAX)) {
    return {
      ok: false,
      error: `kernelSize 必须是 ${CONV_KERNEL_MIN}..${CONV_KERNEL_MAX} 之间的整数，当前为 ${JSON.stringify(kernelSize)}`,
    }
  }
  if (kernelSize > inputRows || kernelSize > inputCols) {
    return {
      ok: false,
      error: `kernelSize (${kernelSize}) 不得大于输入行数/列数 (${inputRows}/${inputCols})`,
    }
  }
  if (stride !== undefined) {
    if (!isIntInRange(stride, CONV_STRIDE_MIN, CONV_STRIDE_MAX)) {
      return {
        ok: false,
        error: `stride 必须是 ${CONV_STRIDE_MIN} 或 ${CONV_STRIDE_MAX}，当前为 ${JSON.stringify(stride)}`,
      }
    }
    return { ok: true, value: { inputRows, inputCols, kernelSize, stride } }
  }
  return { ok: true, value: { inputRows, inputCols, kernelSize, stride: 1 } }
}
