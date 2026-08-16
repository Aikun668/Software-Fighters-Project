# 结构化交互图解改造规格

## 背景与决策

当前图解 Agent 要求模型把完整 HTML/JavaScript 放进 JSON 的 `html_content` 字符串。真实运行已证明这不可靠：HTML 中未转义的引号会使 JSON 解析失败；即使成功解析，后端安全清理也会删除 `script`。前端当前也没有实际渲染该 HTML 的生产链路。

本轮不再让模型生成或执行 HTML。模型只输出受限的结构化图数据，Vue 组件负责 SVG 渲染和节点点击交互。这样模型输出可解析、可校验、可审查，前端行为可控且不需要执行模型生成的脚本。

## 目标与范围

目标：让 `interactive_diagram` 从“静态 fallback 被误当成交互图解”变成可验证的结构化图解产物。

本轮包含：

- 后端图解 Schema v1、确定性校验、确定性 fallback 和 Judge 输入对齐；
- 一个可复用的 Vue SVG 图解组件，支持节点点击查看说明；
- 3 个固定案例的 mock 与真实 smoke 证据；
- diagram 在证据通过前继续运行在 `shadow`，不进入 `active`。

本轮不包含：

- 接通仍为静态演示的资源工坊/对话页与真实 SSE 结果；
- 任意模型生成 JavaScript、HTML 注入、iframe `srcdoc` 或外部 CDN；
- 拖拽、动画、D3.js、任意图形编辑器能力；
- 修改 `content` 的质量门控或解决 content 安全过滤误报。

## 产物契约

`InteractiveDiagramAgent` 的模型输出必须为 JSON，顶层只含：

```json
{
  "diagram": {
    "schema_version": "v1",
    "title": "CNN 数据流",
    "summary": "输入图像依次通过卷积、池化和分类层。",
    "layout": "layered",
    "nodes": [
      {"id": "input", "label": "输入图像", "detail": "原始像素张量", "layer": 0},
      {"id": "conv", "label": "卷积层", "detail": "提取局部特征", "layer": 1}
    ],
    "edges": [
      {"source": "input", "target": "conv", "label": "特征图"}
    ]
  }
}
```

约束：

- `schema_version` 固定 `v1`；`layout` 只允许 `layered` 或 `flow`。
- `title`、`summary`、`label`、`detail`、`edge.label` 都是纯文本；不允许 HTML、URL 或脚本。
- `nodes` 为 2–12 个，`id` 非空且唯一，`layer` 为 0–5 的整数。
- `edges` 为 1–24 条，`source`、`target` 必须引用不同的已有节点；相同有向边不可重复。

Workflow 最终 block 保持现有外层类型，改为：

```python
{
    "type": "interactive_diagram",
    "heading": diagram["title"],
    "content": diagram["summary"],
    "diagram": diagram,
}
```

`content` 只是可读摘要，不再承载 HTML。历史 HTML block 不做自动迁移；渲染器对缺失 `diagram` 的旧 block 显示“旧格式暂不支持交互预览”的安全说明。

## 后端设计

`InteractiveDiagramAgent` 用 `_call_llm_json(..., expected_key="diagram")` 调用模型，并用图解 Schema 校验器作为重试反馈来源。移除 `_validate_html`、`_sanitize_html_output` 和 HTML fallback；改为基于主题与图解类型构造最小结构化 fallback。

`ResourceValidator` 对 `interactive_diagram` 校验完整 Schema，不再仅检查非空 `content`。Judge Prompt 只接收主题、图片摘要、节点和边；它判断主题是否表达清楚、关键节点/关系是否缺失，不接收也不评审 HTML。

`ResourceGenWorkflow` 的三模式和一次 Repair 不变。由于 diagram 的真实证据当前不可用，生产默认维持 `shadow`；即使未来 content 单独满足 active 条件，也不得因此自动把 diagram 切入 active。

## 前端设计

新建受控组件（建议 `frontend/src/components/StructuredDiagram.vue`）：

- 输入：上述 `diagram` 数据；不接收 HTML 字符串。
- SVG 按 `layer` 分列布局；同层节点等距排列，边为箭头线，文本由 Vue 正常转义渲染。
- 点击节点后，在组件内显示 `label` 和 `detail`；键盘聚焦和 Enter/Space 同样可打开详情。
- 响应式宽度、固定 viewBox、无 `v-html`、无 iframe、无外网依赖。
- 缺失或无效 schema 显示简短空状态，不尝试渲染模型原始文本。

当前没有实际消费资源 SSE 结果的前端页面。该组件先以固定 fixture 挂入一个局部演示入口或组件测试，作为渲染能力验证；后续“真实资源结果接入 UI”另立任务，不在本轮伪造已联通的产品能力。

## 失败处理与可观测性

| 场景 | 处理 |
| --- | --- |
| 模型输出非 JSON / 缺少 `diagram` | 使用现有一次重试；仍失败则生成结构化 fallback |
| Schema 不合法 | 在 Agent 内重试一次；最终走结构化 fallback |
| 图解 Judge 不可用 | `review_status=skipped`，交付已通过 Schema 的产物 |
| 前端收到旧 HTML block | 显示安全说明，不执行、不注入 |

运行记录继续保留 `validation_result`、`review_status`、`fallback_used` 和阶段耗时。对图解额外记录 `diagram_schema_version` 与 `diagram_source`（`model` 或 `fallback`）。

## 验收

1. 后端单测覆盖：合法图、重复 ID、悬空边、越界 layer、模型解析失败后 fallback。
2. Workflow mock 测试证明：合法图进入 Judge；不合法图不会直接交付；fallback 仍能通过 Schema Validator。
3. 前端组件测试覆盖：节点与边渲染、点击/键盘详情、无效 schema 空状态；`npm run type-check` 通过。
4. 使用相同 3 个 diagram 案例跑 mock 和真实 Shadow；人工确认每个结果不是 fallback、主题表达正确、节点点击可工作。
5. 仅当以上三例满足且 Judge 与人工标签的分歧已记录，才讨论 diagram 的 `active`。

## 对简历叙事的价值

该改造展示的不是“让 LLM 直接写网页”，而是把不可信生成结果收敛为可验证协议：模型输出 Schema，服务端做结构校验与质量门控，客户端用受控组件渲染。它能清楚说明 Agent 应用中的安全边界、失败降级与端到端可观测性。
