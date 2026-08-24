export type ResourceType = 'document' | 'interactive_diagram'
export type PageState = 'idle' | 'streaming' | 'success' | 'error'
export type ReviewStatus = 'pass' | 'repair' | 'skipped' | 'not_applicable'

export interface ResourceRequest {
  topic: string
  resource_type: ResourceType
}

export interface DiagramNode {
  id: string
  label: string
  detail: string
  layer: number
}

export interface DiagramEdge {
  source: string
  target: string
  label?: string
}

export interface DiagramSchema {
  schema_version: 'v1'
  title: string
  summary: string
  layout: string
  nodes: DiagramNode[]
  edges: DiagramEdge[]
}

export interface ContentBlock {
  type: 'section' | 'callout' | 'code' | 'interactive_diagram' | string
  heading?: string
  content?: string
  language?: string
  diagram?: DiagramSchema
}

export interface DonePayload {
  content_blocks: ContentBlock[]
  questions: unknown[]
  response: string
  error: string
  review_status: ReviewStatus
  repair_attempted: boolean
  fallback_used: boolean
  final_status: string
}

export interface SseEvent {
  type: 'stage_start' | 'stage_end' | 'progress' | 'error' | 'done' | string
  stage?: string
  message?: string
  progress?: number
  data?: DonePayload | unknown
}
