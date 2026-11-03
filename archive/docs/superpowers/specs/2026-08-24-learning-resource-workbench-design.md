# AI 学习资源工作台设计规格

## 1. 目标与定位

新建一套独立、可运行的演示前端：**AI 学习资源工作台**。它不是重做“智学云”全平台，而是把已验证的资源生成 Workflow 变成一条可看、可操作、可解释的用户体验：

```text
输入学习主题 → 选择资源类型 → 实时观看执行进度 → 阅读/交互最终资源 → 查看质量结果
```

它服务于项目演示与简历展示：在两分钟内让用户看懂系统不只是调用模型，而是经由 Director、Specialist、Validator、LLM Judge 和有界 Repair 生成资源。

## 2. 已确认决策

- 新应用目录固定为 `showcase-web/`；它独立于旧 `frontend/`，不向旧页面、Store、Router 或视觉样式追加功能。
- 旧 `frontend/` 保留为历史实现，不删除、不重构、不作为本阶段依赖。
- 第一版只有一个主页面，不做登录、用户中心、课程列表、知识图谱、历史持久化、导出或聊天模式。
- 仅支持两种显式资源类型：`document`（课程资料）与 `interactive_diagram`（交互图解）。它们是已有质量门控与真实证据覆盖的范围。
- 默认后端质量模式保持 `shadow`。前端如实呈现本次评审/修复/降级状态，不暴露“切换 active”控制，也不暗示每次都会修复。
- Codex 负责全部前端设计、实现、测试与联调。DeepSeek 不写任何前端代码；如需要其协作，仅能处理后端契约、后端测试或运行证据。

## 3. 范围与非目标

### 包含

1. 主题输入和类型选择。
2. 使用 Fetch 流式读取 `POST /resources/generate` 的 SSE 响应。
3. 一个简洁的阶段进度展示，消费已有 `stage_start` / `stage_end` 事件。
4. 结构化内容块渲染：`section`、`callout`、`code`、`interactive_diagram`。
5. 图解节点点击后显示节点详情。
6. 最终质量摘要：`review_status`、`repair_attempted`、`fallback_used`、`final_status`。
7. 空态、加载态、输入错误与服务错误的可理解反馈。

### 不包含

- 修改或迁移旧 `frontend/`。
- Java 后端、数据库、认证、登录、用户画像持久化与资源保存。
- 新增 Agent、Prompt、模型、质量规则、质量模式切换或真实模型证据运行。
- 原始 LLM 输出、内部 Prompt、API Key、证据 artifact 的前端展示。
- 复杂动画、拖拽画布、可编辑图解、图表库、Markdown 编辑器或导出能力。

## 4. 应用边界与技术方案

### 目录和运行时

```text
showcase-web/                  # 新 Vue 3 + TypeScript + Vite 应用
  src/
    api/                       # Resource SSE 客户端与协议类型
    components/                # 输入、进度、结果块、图解、质量摘要
    views/                     # 唯一工作台页面
    styles/                    # 全局变量与基础样式
    App.vue
    main.ts
```

采用 Vue 3、TypeScript、Vite 和原生 scoped CSS；不引入 Element Plus、Pinia、图表库或新的 UI 依赖。界面状态仅在当前页面生命周期内存在。

开发服务通过 Vite 代理将 `/ai-api/*` 转发至 AI 服务的 `http://127.0.0.1:8001/internal/*`。这样浏览器请求同源开发地址，不需要为新的 Vite 端口修改 AI 服务 CORS；生产部署策略不在第一版范围内。

### 后端契约

请求：

```http
POST /ai-api/resources/generate
Content-Type: application/json

{
  "topic": "面向初学者解释 Transformer 自注意力机制",
  "resource_type": "document",
  "user_id": 1,
  "student_profile": {}
}
```

该请求由 Vite 代理转发为 AI 服务的 `POST /internal/resources/generate`。前端以 `fetch()` 读取 `ReadableStream` 并自行解析 SSE；不用 `EventSource`，因为它不能发送 POST body。

消费的事件：

- `stage_start` / `stage_end`：更新阶段列表（可出现 `plan`、`generate`、`validate`、`review`、`repair`、`fallback`、`finalize`）。
- `error`：记录为本次过程告警，最终以 `done` 决定是否仍然有可交付结果。
- `done.data`：读取 `content_blocks`、`response`、`error`、`review_status`、`repair_attempted`、`fallback_used`、`final_status`。

前端不依赖 `review_reason`、内部草稿或修复前 artifact，因为当前对外 `done` 契约未提供这些字段。若日后要展示“为何修复”，必须单独定义脱敏的 API 契约与测试，不能从日志或证据目录读取。

## 5. 页面体验

页面采用一个响应式工作台，桌面端为左侧控制区、右侧结果区；窄屏时上下堆叠。

```text
┌─────────────────────────────────────────────────────────────┐
│ 学习资源工作台                         生成可阅读的学习材料   │
├───────────────┬─────────────────────────────────────────────┤
│ 你想学什么？   │  初始：说明工作台可生成什么                  │
│ [主题输入框]  │  生成中：阶段进度（不展示内部 Prompt）         │
│               │  完成后：资源标题、摘要、内容块/交互图解       │
│ 资源形式      │           质量摘要卡                           │
│ [课程资料]    │                                               │
│ [交互图解]    │                                               │
│               │                                               │
│ [开始生成]    │                                               │
└───────────────┴─────────────────────────────────────────────┘
```

### 输入区

- 主题为必填，前端 `trim()` 后为空时不发请求，提示“请输入想学习的主题”。
- 两个类型选择按钮带说明：课程资料用于分节讲解；交互图解用于查看概念关系或流程。
- 提供 2–3 个仅填充输入框的示例主题，不自动发起请求。
- 生成中禁用输入与按钮，并提供“正在生成，可稍候”的状态；不实现取消请求。

### 过程区

- 用有限的阶段名称展示过程：规划、生成、结构检查、质量评审、修复（仅出现时）、结果整理。
- 收到阶段开始时标为进行中，阶段结束后标为完成；未出现的可选阶段不显示为失败。
- `error` 事件显示为低优先级过程提示，除非最终 `done` 的 `final_status` 不是 `success` 或没有可渲染产物。

### 结果区

- `section`：标题和正文；正文使用安全的纯文本换行渲染，不使用 `v-html`。
- `callout`：视觉上与 section 区分，但不改变内容。
- `code`：使用 `<pre><code>` 纯文本显示，不执行或高亮模型生成代码。
- `interactive_diagram`：只接受 Schema v1，使用受控 SVG 渲染；节点可点击/键盘操作以展示 `detail`。无效 Schema 显示稳定的不可交互提示，不回退到模型 HTML。
- 未识别块类型忽略并记录开发期控制台警告，不能让整页崩溃。

### 质量摘要

结果区域底部用简短、面向用户的语言展示：

- `review_status=pass`：已完成质量检查。
- `review_status=repair` 且 `repair_attempted=false`：发现可改进项，当前以观察模式保留原结果。
- `review_status=skipped`：质量评审暂不可用，已交付通过结构检查的结果。
- `repair_attempted=true`：已执行一次受限修复。
- `fallback_used=true`：已使用兼容的课程资料降级结果。
- `final_status!=success` 或无产物：显示可重试错误态，不展示“生成成功”。

状态文案须如实反映 `shadow` / 降级语义，不能把 Judge 的结论描述成事实正确性保证。

## 6. 状态模型与错误处理

页面状态固定为：`idle | streaming | success | error`。

- 新请求开始时清空上一次事件、结果和质量摘要。
- 流解析失败、HTTP 非 2xx、未收到有效 `done`，进入 `error`，保留用户输入以便重试。
- 收到 `done` 且有 `content_blocks`，即使 Judge 为 `skipped` 或中间有 `error` 事件，也按 `success` 展示；质量摘要说明降级事实。
- 同一次请求的并发点击由 disabled 防止；不做请求队列或历史管理。

## 7. 验收标准

### 前端自动化

- SSE 解析器可处理被任意分割的 chunk、多个事件和结尾残片。
- 输入为空不会发请求；请求体只含当前主题、资源类型、演示用 `user_id=1` 和空画像。
- `done` 事件正确映射为内容与质量摘要；`skipped`、repair、fallback、错误结果均有测试。
- `section`、`callout`、`code` 可安全渲染；无效 diagram 不会使用 HTML，合法 Schema v1 节点可点击并显示详情。
- `npm run type-check` 与 `npm test` 通过。

### 联调验收

1. AI 服务启动于 8001，工作台可通过 Vite 代理调用它。
2. 课程资料请求能从 `stage_start`/`stage_end` 看到过程，并显示 `done.content_blocks`。
3. 图解请求能渲染 Schema v1 且节点可交互；模型产物无效时显示安全提示。
4. 所有可见质量状态都与最终 `done` payload 一致。
5. 演示者可在不登录、不启动 Java/MySQL/Redis 的情况下完成一次生成演示。

## 8. 后续实施顺序

1. 在 `showcase-web/` 建立最小独立工程和 Vite 代理，先验证健康检查与接口可达性。
2. 实现 POST SSE 客户端、协议类型与单元测试。
3. 实现页面状态机、输入区和过程区。
4. 实现内容块、结构化图解与质量摘要。
5. 完成真实联调、截图/演示走查和类型/测试验证。

实现阶段的详细任务、文件清单与测试命令将在本规格获得用户确认后写入 `docs/superpowers/plans/`。
