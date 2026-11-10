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
  schema_version: string
  title: string
  summary: string
  layout: 'layered' | 'flow'
  nodes: DiagramNode[]
  edges: DiagramEdge[]
}
