# 智学 Tutor · Attention 可视化组件落地说明

## 目标
不重做现有学习平台 UI。保留暖米白背景与陶土色用户消息，只在回答中的算法/矩阵演示区域增加一套「雾蓝信息可视化」语言。

## 设计 Token
```css
:root {
  --surface-page: #FAF9F6;
  --surface-sidebar: #F3F0E9;
  --surface-card: #FFFEFC;
  --text-primary: #27343A;
  --text-secondary: #77817F;
  --border-subtle: #E8E5DE;
  --brand-clay: #A76F5D;
  --viz-blue: #80AEC8;
  --viz-blue-strong: #447F9F;
  --viz-blue-pale: #ECF4F8;
  --viz-cell: #CDE2EE;
  --viz-disabled: #F0F0ED;
  --positive-sage: #719E89;
}
```

## 页面层级
- 不动侧边栏和整体聊天布局。
- assistant 回答使用白卡，最大宽度约 860–900px；卡内 24–30px padding。
- 标题（20–24px）→ 2 个概念对照小卡 → 正确渲染公式 → 可交互矩阵 → 关键结论。
- 矩阵交互卡：头部 56–70px，控制栏 46px，内容两列（左：矩阵，右：当前格子解释），底部说明。
- 小于 740px 时：矩阵和右侧说明上下排列，不横向溢出；格子 gap 减小。

## Vue 组件
`AttentionMatrix.vue` 负责图形及交互，建议 Props：
```ts
type AttentionMatrixProps = {
  tokenCount: number;             // 3..8 为 MVP 演示范围
  mode: 'causal' | 'bidirectional';
  queryLabels?: string[];
  keyLabels?: string[];
  weights?: number[][];           // 可选真实注意力权重；没有时不画成强弱热力图
};
```

MVP 交互：
1. 因果模式：`visible(i,j) = j <= i`，灰色表示不可访问；双向模式全部可访问。
2. Token 3–8 数量可调，矩阵实时重建；点允许访问的格子显示 `Qi → Kj`、状态及解释。
3. 已选中格子用深雾蓝，选中行中其他可访问格子用较深雾蓝，普通允许访问格子用浅雾蓝；不允许的格子禁用且不可点击。
4. 左轴 = Query，顶轴 = Key。统计允许访问的格子数：因果 `n(n+1)/2`，双向 `n²`。
5. 必须在图例写明：「颜色表示 Mask/可访问关系，不代表真实 Attention 权重」；有真实权重才允许展示强弱比例或概率值。
6. 支持键盘焦点、可读的 aria-label、tooltip、移动端缩放。

## 与 Agent 消息流对接
不要要求 LLM 直接输出不受控的 HTML/Vue 代码。推荐由内容层输出独立的结构化 UI block，再交由前端 renderer registry 分发：
```json
{
  "type": "attention_matrix",
  "version": 1,
  "props": { "tokenCount": 5, "mode": "causal" }
}
```
前端对 type/version/props 做 schema 验证；组件独立于普通 Markdown 正文，也可以由后端在内容生成后作为 `visualization` 事件发送。

## 文本渲染先修好
参考截图中，部分 `$n$`、`**token**` 在你自己的平台上仍以原始字符出现。先排查流式增量 Markdown 与公式渲染，推荐 `markdown-it` + `KaTeX`，或 `remark`/`rehype` 生态。流式阶段可以保留原文缓冲，按完成的块渲染，避免 LaTeX/Markdown 被不完整 token 打断。不要通过 AI 提示词来修复渲染器问题。

## 验收
- 默认 5 Token 因果注意力：25 格，15 个可访问，10 个灰色。
- 切到双向注意力：25 个都可以访问；切回因果注意力：恢复 15 个。
- 拖到 8 Token 因果模式：64 格，36 个可访问。
- 点击 Q5/K3 显示可访问；Q2/K5 在因果模式被禁用。
- 移动端不横向溢出、不破坏原有聊天视觉规范。
- 无真实权重时，不输出任何伪造的强弱或概率。

本目录 `tutor_attention_design.html` 是不依赖框架的可运行视觉原型，不等于已接入项目的 Vue 组件。
