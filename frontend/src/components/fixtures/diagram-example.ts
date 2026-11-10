import type { DiagramSchema } from '@/types/diagram'

export const exampleDiagram: DiagramSchema = {
  schema_version: 'v1',
  title: 'CNN 数据流',
  summary: '输入图像依次通过卷积、池化和分类层。',
  layout: 'layered',
  nodes: [
    { id: 'input', label: '输入图像', detail: '原始像素张量', layer: 0 },
    { id: 'conv', label: '卷积层', detail: '提取局部特征', layer: 1 },
    { id: 'pool', label: '池化层', detail: '降低维度', layer: 1 },
    { id: 'fc', label: '全连接层', detail: '输出分类', layer: 2 },
  ],
  edges: [
    { source: 'input', target: 'conv', label: '特征图' },
    { source: 'conv', target: 'pool', label: '降维' },
    { source: 'pool', target: 'fc', label: '分类' },
  ],
}

// 旧格式 / 非法 schema，用于验证空状态
export const legacyDiagram = { schema_version: 'v9', title: '', summary: '', layout: 'layered', nodes: [], edges: [] }
