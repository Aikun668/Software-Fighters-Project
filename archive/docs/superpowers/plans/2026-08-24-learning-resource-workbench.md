# AI 学习资源工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建独立的 `showcase-web/`，让用户输入学习主题后通过 SSE 看到资源生成过程，并阅读课程资料或操作结构化交互图解。

**Architecture:** 新前端是独立的 Vue 3 + TypeScript + Vite 应用，不依赖旧 `frontend/` 的路由、Store 或组件体系。它通过 Vite `/ai-api` 代理调用 Python AI 服务的 `POST /resources/generate`，用一个页面状态机管理输入、流式阶段、结果块和质量摘要。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、jsdom、原生 Fetch ReadableStream、原生 CSS；不新增运行时依赖。

**Spec:** `docs/superpowers/specs/2026-08-24-learning-resource-workbench-design.md`

## Global Constraints

- 新应用目录固定为 `showcase-web/`；不修改旧 `frontend/`。
- DeepSeek 不实现前端；本计划中的所有前端任务由 Codex 完成。
- 第一版只支持 `document` 与 `interactive_diagram`。
- 默认后端质量模式保持 `shadow`，前端如实显示 `pass`、`repair`、`skipped`、降级和最终状态。
- 不使用 Element Plus、Pinia、图表库、Markdown 渲染器、`v-html`、iframe、CDN 或模型生成脚本。
- 图解只渲染 Schema v1；非法图解显示稳定提示，不执行或解析模型 HTML。
- 不改 Java、数据库、认证、旧前端、LLM Provider、Prompt 和质量门控逻辑。
- 每项实现先写失败测试，再写最小实现；每个 Task 完成后运行自己的测试并单独提交。

---

## 文件结构

```text
showcase-web/
├── index.html、package.json、tsconfig*.json、vite.config.ts、vitest.config.ts
└── src/
    ├── App.vue、main.ts、vite-env.d.ts
    ├── api/resourceSse.ts + resourceSse.test.ts
    ├── types/resource.ts
    ├── components/ResourceInputPanel.vue
    ├── components/WorkflowTimeline.vue
    ├── components/ResourceResult.vue
    ├── components/ContentBlockRenderer.vue
    ├── components/StructuredDiagram.vue
    ├── components/QualitySummary.vue
    ├── views/ResourceWorkbenchView.vue
    ├── styles/base.css
    └── test/setup.ts
```

API 模块只负责请求和 SSE 解析；类型文件只负责契约；展示组件只负责渲染；`ResourceWorkbenchView` 持有唯一页面状态；`App.vue` 只提供应用壳。

## 前端契约

在 `src/types/resource.ts` 定义 `ResourceType = 'document' | 'interactive_diagram'`、`PageState = 'idle' | 'streaming' | 'success' | 'error'`、`ReviewStatus = 'pass' | 'repair' | 'skipped' | 'not_applicable'`，以及 `DiagramNode`、`DiagramEdge`、`DiagramSchema(v1)`、`ContentBlock`、`DonePayload`、`SseEvent` 类型。字段名称必须与 Python 服务的 `done` payload 对齐：`content_blocks`、`response`、`review_status`、`repair_attempted`、`fallback_used`、`final_status`。

`generateResource(request, onEvent, signal?) -> Promise<DonePayload>` 固定向 `/ai-api/resources/generate` 发 POST，body 为 `topic`、`resource_type`、`user_id: 1`、`student_profile: {}`。用 `fetch` 读取 `ReadableStream`，不用 `EventSource`，因为请求需要 POST body。解析器使用增量 `TextDecoder`，保留跨 chunk 的 buffer，按空行分帧，解析 `data:` 行；非 2xx、非法 JSON、流结束没有 done、AbortSignal 中断都转成可测试异常。

---

### Task 1: 建立独立 showcase-web 工程

**Files:** 创建 `showcase-web/package.json`、`index.html`、`.gitignore`、`tsconfig.json`、`tsconfig.app.json`、`tsconfig.node.json`、`vite.config.ts`、`vitest.config.ts`、`src/main.ts`、`src/App.vue`、`src/vite-env.d.ts`、`src/test/setup.ts`、`src/styles/base.css` 和后续页面接入前的 `src/views/ResourceWorkbenchView.vue` 最小占位页。

**Produces:** port `5174` 的 Vite 应用；`/ai-api/*` 代理到 `http://127.0.0.1:8001/internal/*`；后续测试共用的 Vitest/jsdom 配置。

- [ ] **Step 1: 创建工程和基础入口**

脚本至少包含 `dev`、`build`、`build-only`、`type-check`、`test`；依赖只使用 Vue、Vue plugin、TypeScript、Vite、Vitest、jsdom、Vue Test Utils 和 `npm-run-all2`，不复制旧前端业务依赖。

- [ ] **Step 2: 配置代理和应用壳**

Vite 配置使用 `server.port = 5174`，代理 target 为 `http://127.0.0.1:8001`，rewrite 为 `path.replace(/^\/ai-api/, '/internal')`。`App.vue` 只渲染 `ResourceWorkbenchView`，不引入旧 `frontend/` 的 `Home.vue` 或 Router。

- [ ] **Step 3: 验证并提交**

Run: `cd showcase-web; npm install; npm run type-check; npm test; npm run build-only`

Expected: 全部 PASS。提交：`git add showcase-web; git commit -m "feat: scaffold learning resource showcase"`。

### Task 2: 实现类型和 POST SSE 客户端

**Files:** 创建 `showcase-web/src/types/resource.ts`、`showcase-web/src/api/resourceSse.ts`、`showcase-web/src/api/resourceSse.test.ts`。

**Consumes:** Task 1 的 `/ai-api` 代理。**Produces:** `generateResource(request, onEvent, signal?) -> Promise<DonePayload>`。

- [ ] **Step 1: 写失败测试**

覆盖事件被拆成多个 chunk、多个事件连续出现、结尾残片、非法 JSON、非 2xx、没有 done、AbortSignal。必须有跨 chunk JSON 的测试，例如把 `data: {"type":"stage_start"...}` 拆在两个字符串中再断言事件正常回调。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- src/api/resourceSse.test.ts`。Expected: FAIL，因为类型和客户端函数尚不存在。

- [ ] **Step 3: 实现最小客户端**

读取循环固定执行：`fetch` → `response.ok/body` 检查 → `TextDecoder.decode(..., { stream: true })` → buffer 按空行取帧 → 解析 `data:` 行 → 调用 `onEvent` → `done` 返回。禁止客户端自动重试模型请求；异常交给页面显示“重新生成”。

- [ ] **Step 4: 验证并提交**

Run: `npm test -- src/api/resourceSse.test.ts`。Expected: 全部 PASS。提交：`git add showcase-web/src/types showcase-web/src/api; git commit -m "feat: add resource SSE client"`。

### Task 3: 实现输入、状态机和过程时间线

**Files:** 创建 `ResourceInputPanel.vue`、`WorkflowTimeline.vue`、`ResourceWorkbenchView.vue` 及对应测试；修改 `showcase-web/src/App.vue`。

**Produces:** 输入组件通过 `submit(topic, resourceType)` 输出；时间线只读接收 `SseEvent[]`；页面持有 `PageState`、当前类型、主题、事件、done 和错误。

- [ ] **Step 1: 写失败测试**

覆盖空主题不发请求并显示“请输入想学习的主题”、streaming 禁用提交、stage 事件进入时间线、done 后显示结果、skipped 仍显示结果、异常进入 error 且保留主题。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- src/components/ResourceInputPanel.test.ts src/views/ResourceWorkbenchView.test.ts`。Expected: FAIL，因为组件和页面行为尚不存在。

- [ ] **Step 3: 实现输入区**

提供 `textarea maxlength=2000`、课程资料/交互图解两个选择按钮、2–3 个只填充输入框的示例主题和 submit 按钮。`trim()` 为空时不发请求；streaming 时禁用输入和按钮。

- [ ] **Step 4: 实现状态机和时间线**

阶段映射固定为：`plan=规划资源`、`generate=生成内容`、`validate=结构检查`、`review=质量评审`、`repair=受限修复`、`fallback=兼容降级`、`finalize=整理结果`。每次提交清空旧数据；事件追加时间线；done 设置 success；异常设置 error；不引入全局 Store、请求队列或取消功能。

- [ ] **Step 5: 验证并提交**

Run: `npm test -- src/components/ResourceInputPanel.test.ts src/views/ResourceWorkbenchView.test.ts; npm run type-check`。Expected: PASS。提交：`git add showcase-web/src/App.vue showcase-web/src/components showcase-web/src/views; git commit -m "feat: add resource workflow input and timeline"`。

### Task 4: 实现内容块、结构化图解和结果容器

**Files:** 创建 `ContentBlockRenderer.vue`、`StructuredDiagram.vue`、`ResourceResult.vue` 及三组组件测试。

**Consumes:** `DonePayload.content_blocks`。**Produces:** section、callout、code、interactive_diagram 四类块的安全渲染；图解节点点击、Enter、Space 显示 detail。

- [ ] **Step 1: 写失败测试**

证明 section/callout/code 是纯文本，合法 Schema v1 图解可渲染并显示节点详情，非法图解显示“旧格式暂不支持交互预览”而不创建 SVG/HTML。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- src/components/ContentBlockRenderer.test.ts src/components/StructuredDiagram.test.ts src/components/ResourceResult.test.ts`。Expected: FAIL，因为展示组件尚不存在。

- [ ] **Step 3: 实现安全内容块渲染**

`section`、`callout`、`code` 使用 Vue 插值和 `<pre><code>`；不使用 `v-html`。interactive_diagram 只把 `block.diagram` 传给受控图解组件；未知类型不能让整页崩溃。

- [ ] **Step 4: 实现受控 SVG 图解**

只接受 `schema_version === 'v1'` 且节点/边结构有效的输入。按 layer 确定性排列节点，用 SVG line/circle/text 绘制；节点具备 `role=button`、`tabindex=0` 和 Enter/Space 操作。禁止 D3、拖拽、iframe、HTML、脚本。

- [ ] **Step 5: 验证并提交**

`ResourceResult` 按顺序渲染 blocks 和 response；没有 blocks 时显示结果不可用，不伪造成功内容。Run: `npm test -- src/components/ContentBlockRenderer.test.ts src/components/StructuredDiagram.test.ts src/components/ResourceResult.test.ts; npm run type-check`。Expected: PASS。提交：`git add showcase-web/src/components; git commit -m "feat: render learning resources and diagrams"`。

### Task 5: 接入质量摘要、视觉系统和联调

**Files:** 创建 `QualitySummary.vue` 及测试；修改 `ResourceWorkbenchView.vue`、`styles/base.css`、`App.vue`。

**Consumes:** `reviewStatus`、`repairAttempted`、`fallbackUsed`、`finalStatus`。**Produces:** 面向用户的真实质量摘要，不声称事实正确性，不暴露内部实现细节。

- [ ] **Step 1: 写质量摘要失败测试**

固定映射：`pass → 已完成质量检查`；`repair 且未执行 → 发现可改进项，当前保留原结果`；`skipped → 质量评审暂不可用，已交付结构检查通过的结果`；`repair_attempted=true → 已执行一次受限修复`；`fallback_used=true → 已使用兼容的课程资料结果`；`final_status` 非 success → 生成未完成，可重新生成。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- src/components/QualitySummary.test.ts`。Expected: FAIL，因为摘要组件不存在。

- [ ] **Step 3: 实现摘要并接入结果区**

默认 shadow 下 repair 且未执行时必须明确写“当前保留原结果”；不展示内部 Prompt、artifact 或日志，不把 Judge 结论描述成事实正确性保证。

- [ ] **Step 4: 完成克制视觉系统**

在 `base.css` 定义浅色背景、深色文字、蓝色主操作色、边框、圆角和 focus 样式。桌面端左输入右结果，窄屏上下排列；不添加复杂动画、渐变背景、浮动粒子或旧平台导航。

- [ ] **Step 5: 完整验证**

Run: `npm test; npm run type-check; npm run build`。Expected: 全部 PASS。

- [ ] **Step 6: 真实联调和提交**

启动 `ai-service` 的 8001 服务与 `showcase-web` 的 5174 服务，分别验证课程资料和交互图解：能看到阶段进度、内容结果、图解节点详情和质量摘要；空主题、服务不可达、无效图解均有稳定反馈；确认旧 `frontend/` 没有变化。提交：`git add showcase-web; git commit -m "feat: complete learning resource workbench"`。

## Final Verification

- [ ] `showcase-web/npm test`、`npm run type-check`、`npm run build` 全部通过。
- [ ] 两种资源类型完成真实联调。
- [ ] 旧 `frontend/`、Java 后端和 Python 质量门控没有非计划变更。
- [ ] 未生成或提交密钥、日志、JSONL、artifact。
- [ ] 演示文档只引用实际可见行为，不把 `shadow` 描述成默认主动修复。
