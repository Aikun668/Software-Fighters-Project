# Design Document Interaction Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the static demo’s conversation, sidebar, and five learning modules behave according to the approved layout and interaction documents.

**Architecture:** Add one front-end-only Pinia store for conversations, drafts, current mode, and linked artefacts. `Home.vue` consumes that store for the sidebar; `QuestionNavChat.vue` consumes it for empty and active conversation states. The five existing module pages retain their local mock data and exchange context using router query parameters.

**Tech Stack:** Vue 3 Composition API, TypeScript, Pinia, Vue Router, Lucide Vue, Vite, Playwright CLI browser checks.

## Global Constraints

- Do not call back-end APIs, Agents, SSE, databases, or real export services.
- Preserve the approved warm ivory, line-icon, editorial visual system and existing shell layout.
- Every visible P0/P1 action in `temp_file/design-file` must perform a visible local state transition, navigation, confirmation, modal, or toast.
- Keep existing routes working; redirects from legacy routes remain intact.
- Use `npm run build` and local browser checks after every independently testable task.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `frontend/src/stores/demoConversation.ts` | Shared static conversation data, mode, drafts, session links, local persistence helpers. |
| `frontend/src/views/Home.vue` | Sidebar conversation selection, rename/delete actions, local UI menus and persistence. |
| `frontend/src/views/QuestionNavChat.vue` | Empty state modes, active chat state, composer, message actions, title bar and session panel. |
| `frontend/src/router/index.ts` | Preserve context query parameters for inter-module navigation. |
| `frontend/src/views/LearningAnalysisPage.vue` | Make diagnostic tabs/drawer and correction feedback actionable. |
| `frontend/src/views/LearningPlanPage.vue` | Make plan controls and graph context navigation actionable. |
| `frontend/src/views/KnowledgeGraphPage.vue` | Confirm node removal, consume `nodeId`, and provide contextual navigation. |
| `frontend/src/views/ExerciseCenterPage.vue` | Make skip/history/context actions deterministic. |
| `frontend/src/views/ResourceCenterPage.vue` | Make resource-to-chat context explicit and export feedback non-blocking. |

## Task 1: Create the static conversation state store

**Files:**
- Create: `frontend/src/stores/demoConversation.ts`

**Interfaces:**
- Produces `ChatMode = 'auto' | 'exercise' | 'resource' | 'plan' | 'visualization'`.
- Produces `DemoConversation`, `DemoMessage`, and `useDemoConversationStore()`.
- Store methods: `createConversation(mode)`, `selectConversation(id)`, `sendMessage(content, mode)`, `renameConversation(id, title)`, `deleteConversation(id)`, `setDraft(id, value)`, `setMode(mode)`, `toggleSessionPanel()`.

- [ ] **Step 1: Add the store contract and fixed seed data.**

```ts
export type ChatMode = 'auto' | 'exercise' | 'resource' | 'plan' | 'visualization'
export interface DemoMessage { id: string; role: 'user' | 'assistant'; content: string; mode: ChatMode; createdAt: string; reaction?: 'up' | 'down' }
export interface DemoConversation { id: string; title: string; mode: ChatMode; createdAt: string; messages: DemoMessage[]; draft: string; panelOpen: boolean; links: { nodeId?: string; exerciseId?: string; resourceId?: string; planId?: string } }
```

- [ ] **Step 2: Verify the pre-change browser state fails the intended interaction.**

Run: `npx --yes --package @playwright/cli playwright-cli -s=alignment open http://127.0.0.1:5173/question-nav-chat`

Expected: the page has no five-card mode grid and no conversation title bar after sending a message.

- [ ] **Step 3: Implement the Pinia store with local persistence.**

```ts
const storageKey = 'zhixue-demo-conversations'
const conversations = ref<DemoConversation[]>(loadSeedOrStorage())
const activeId = ref<string | null>(conversations.value[0]?.id ?? null)
const activeConversation = computed(() => conversations.value.find(item => item.id === activeId.value) ?? null)

function persist() { localStorage.setItem(storageKey, JSON.stringify({ conversations: conversations.value, activeId: activeId.value })) }
function createConversation(mode: ChatMode = 'auto') {
  const conversation: DemoConversation = { id: crypto.randomUUID(), title: '新建对话', mode, createdAt: new Date().toLocaleString('zh-CN'), messages: [], draft: '', panelOpen: false, links: {} }
  conversations.value.unshift(conversation); activeId.value = conversation.id; persist(); return conversation
}
function sendMessage(content: string, mode: ChatMode) {
  const conversation = activeConversation.value ?? createConversation(mode)
  conversation.mode = mode
  conversation.messages.push({ id: crypto.randomUUID(), role: 'user', content, mode, createdAt: new Date().toLocaleTimeString('zh-CN') })
  conversation.messages.push({ id: crypto.randomUUID(), role: 'assistant', content: fixedReplyByMode(mode, content), mode, createdAt: new Date().toLocaleTimeString('zh-CN') })
  if (conversation.title === '新建对话') conversation.title = content.slice(0, 18)
  conversation.draft = ''; persist()
}
```

- [ ] **Step 4: Verify type safety and production build.**

Run: `npm run build`

Expected: exit code `0`.

- [ ] **Step 5: Commit the isolated store.**

```bash
git add frontend/src/stores/demoConversation.ts
git commit -m "feat: add static conversation demo store"
```

## Task 2: Align sidebar conversation management

**Files:**
- Modify: `frontend/src/views/Home.vue`
- Modify: `frontend/src/router/index.ts`

**Consumes:** `useDemoConversationStore()` from Task 1.

**Produces:** Sidebar navigation that writes `conversationId` and preserves collapse/history state in localStorage.

- [ ] **Step 1: Add failing browser checks for state propagation.**

Run: open `/question-nav-chat`, click `新建对话`, then inspect the URL.

Expected before implementation: URL has no `conversationId` and historic rows do not select a distinct conversation.

- [ ] **Step 2: Replace the hard-coded `conversations` array with store state.**

```ts
const conversationStore = useDemoConversationStore()
const currentConversationId = computed(() => String(route.query.conversationId ?? conversationStore.activeId ?? ''))
function openConversation(id: string) {
  conversationStore.selectConversation(id)
  router.push({ path: '/question-nav-chat', query: { ...route.query, conversationId: id } })
}
function newConversation() {
  const conversation = conversationStore.createConversation('auto')
  router.push({ path: '/question-nav-chat', query: { conversationId: conversation.id, mode: 'auto' } })
}
```

- [ ] **Step 3: Add hover actions for rename and delete.**

```vue
<button class="conversation-more" @click.stop="menuFor = item.id">⋯</button>
<div v-if="menuFor === item.id" class="conversation-menu">
  <button @click="startRename(item)">重命名</button>
  <button @click="deleteTarget = item">删除对话</button>
</div>
```

Delete must show the document-defined confirmation copy and select the next available conversation after confirmation.

- [ ] **Step 4: Persist sidebar state.**

```ts
const collapsed = useLocalStorage('zhixue-sidebar-collapsed', false)
const historyOpen = useLocalStorage('zhixue-history-open', true)
```

If VueUse is not used in the file, use small `onMounted`/`watch` localStorage helpers instead of adding a dependency.

- [ ] **Step 5: Browser verification.**

Run: create a conversation, rename it, reload the browser, select it, delete it, then inspect the sidebar and `/question-nav-chat?conversationId=...` URL.

Expected: selected state, changed title, deletion fallback, and collapse/history settings survive reload.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/views/Home.vue frontend/src/router/index.ts
git commit -m "feat: align sidebar conversation controls"
```

## Task 3: Implement document-accurate chat modes and empty state

**Files:**
- Modify: `frontend/src/views/QuestionNavChat.vue`

**Consumes:** `ChatMode`, `useDemoConversationStore()`, router query values `conversationId`, `mode`, and `topic`.

**Produces:** Five mode cards, a working mode selector, mode-specific composer, and active conversation layout.

- [ ] **Step 1: Add the mode definition table in the component.**

```ts
const modeDefinitions: Record<ChatMode, { label: string; description: string; placeholder: string; example: string; icon: Component }> = {
  auto: { label: '自动', description: '有问题直接问，系统智能判断意图', placeholder: '输入你的问题，或点击上方卡片快速开始...', example: 'CNN 的卷积是怎么算的', icon: Sparkles },
  exercise: { label: '出题练习', description: '生成练习题检验掌握程度', placeholder: '说明想练习的知识点和题目类型...', example: '出 5 道 CNN 选择题', icon: PencilLine },
  resource: { label: '资源生成', description: '生成结构化学习资料', placeholder: '输入主题，我生成学习资料...', example: '整理一份 Transformer 入门资料', icon: FolderOpen },
  plan: { label: '学习路径', description: '规划个性化学习路线', placeholder: '告诉我你的目标和当前基础...', example: '帮我规划一个 NLP 学习路线', icon: Map },
  visualization: { label: '可视化', description: '生成图表、计算图或示意图', placeholder: '描述你希望看见的图或过程...', example: '画一张反向传播的计算图', icon: BarChart3 }
}
```

Import `Component` from `vue`; import `Sparkles`, `PencilLine`, `FolderOpen`, `Map`, and `BarChart3` from `@lucide/vue-next`.

- [ ] **Step 2: Replace the current three text shortcuts with the five-card grid.**

```vue
<button v-for="mode in modeList" :key="mode.key" class="mode-card" @click="selectMode(mode.key)">
  <component :is="mode.icon" :size="20" />
  <strong>{{ mode.label }}</strong>
  <span>{{ mode.example }}</span>
</button>
```

`selectMode()` must set the store mode and composer text to the example, but must not send a message.

- [ ] **Step 3: Implement the active conversation view.**

```vue
<header class="conversation-header">
  <div><h1>{{ activeConversation.title }}</h1><small>模式：{{ modeLabel }} · 创建于 {{ activeConversation.createdAt }} · {{ activeConversation.messages.length }} 条消息</small></div>
  <div><button @click="renaming = true">重命名</button><button @click="deleteTarget = activeConversation">删除</button><button @click="exportConversation">导出</button></div>
</header>
```

Render user messages right-aligned and assistant messages left-aligned with copy, regenerate, and reaction controls. Regenerate replaces only the selected assistant message with a deterministic mode-specific reply.

- [ ] **Step 4: Add the collapsible right session panel.**

It must expose current mode and navigation buttons for the conversation’s linked resource, exercise, plan, or graph node. Its closed form is a 48px rail, its open form is 280px.

- [ ] **Step 5: Browser verification.**

Run the following checks in one session:

```bash
npx --yes --package @playwright/cli playwright-cli -s=alignment open http://127.0.0.1:5173/question-nav-chat
# click each mode card; verify composer text changes and no reply is created
# send resource mode prompt; verify a resource-style assistant result and active header
# open/close session panel; click copy/regenerate/reaction controls
```

Expected: all five cards, selector options, composer labels, active message layout, and session panel state are visible.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/views/QuestionNavChat.vue
git commit -m "feat: align chat modes and conversation states"
```

## Task 4: Add cross-module context contracts

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/LearningAnalysisPage.vue`
- Modify: `frontend/src/views/LearningPlanPage.vue`
- Modify: `frontend/src/views/KnowledgeGraphPage.vue`
- Modify: `frontend/src/views/ExerciseCenterPage.vue`
- Modify: `frontend/src/views/ResourceCenterPage.vue`

**Consumes:** Query names `mode`, `topic`, `nodeId`, `exerciseId`, `resourceId`, `planId`.

**Produces:** Every cross-module navigation explains its origin by selecting/focusing the target mock item.

- [ ] **Step 1: Establish route helpers in each relevant component.**

```ts
function goToChat(mode: ChatMode, topic?: string) {
  router.push({ path: '/question-nav-chat', query: { mode, ...(topic ? { topic } : {}) } })
}
function goToGraph(nodeId: string) { router.push({ path: '/learning-resource-network', query: { nodeId } }) }
```

- [ ] **Step 2: Consume target context on destination pages.**

```ts
watch(() => route.query.nodeId, nodeId => {
  if (typeof nodeId === 'string' && nodes.some(node => node.id === nodeId)) selected.value = nodeId
}, { immediate: true })
```

Use the same immediate route-query selection pattern for `exerciseId`, `resourceId`, and `planId`.

- [ ] **Step 3: Verify each document-defined bridge.**

Run browser flows:

1. 学情分析「线性代数基础薄弱」→ 图谱聚焦 `linear` → 专项练习。
2. 资源工坊「去对话生成」→ `/question-nav-chat?mode=resource`。
3. 学习计划「查看图谱位置」→ 图谱对应节点。
4. 练习反馈「查看相关资源」→ 资源工坊预览对应资源。

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/router/index.ts frontend/src/views/LearningAnalysisPage.vue frontend/src/views/LearningPlanPage.vue frontend/src/views/KnowledgeGraphPage.vue frontend/src/views/ExerciseCenterPage.vue frontend/src/views/ResourceCenterPage.vue
git commit -m "feat: preserve learning context across modules"
```

## Task 5: Complete the analysis and plan button audits

**Files:**
- Modify: `frontend/src/views/LearningAnalysisPage.vue`
- Modify: `frontend/src/views/LearningPlanPage.vue`

**Consumes:** Current mock data and Task 4 navigation helpers.

**Produces:** No inert visible actions in these two pages.

- [ ] **Step 1: Make diagnosis drawer tabs filter local diagnoses.**

```ts
const diagnosisFilter = ref<'全部' | '需关注' | '正在进步' | '计划风险'>('全部')
const visibleDiagnoses = computed(() => diagnosisFilter.value === '全部' ? diagnoses : diagnoses.filter(item => item.group === diagnosisFilter.value))
```

- [ ] **Step 2: Make the profile correction dialog save visible feedback.**

Submitting correction must close the dialog and show `已记录你的反馈，后续画像会优先参考。` without modifying objective mastery scores.

- [ ] **Step 3: Make plan operations complete their document-defined local outcomes.**

- Plan selector changes title, overview count, and timeline data.
- New plan opens a modal with a goal input; confirmation prepends `{ id: crypto.randomUUID(), title: goal, completed: 0, total: 0, tasks: [] }`, selects it, and closes the modal.
- Task delete requires confirmation; task completion updates completed count and current module progress.
- AI adjustment preview only applies changes after `应用调整`.

- [ ] **Step 4: Browser verification.**

Open each page, click every visible button once, and record the resulting state in the browser snapshot. No click may silently do nothing.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/views/LearningAnalysisPage.vue frontend/src/views/LearningPlanPage.vue
git commit -m "feat: complete analysis and plan interactions"
```

## Task 6: Complete graph, exercise, and resource button audits

**Files:**
- Modify: `frontend/src/views/KnowledgeGraphPage.vue`
- Modify: `frontend/src/views/ExerciseCenterPage.vue`
- Modify: `frontend/src/views/ResourceCenterPage.vue`

**Consumes:** Task 4 route context helpers.

**Produces:** Confirmed destructive actions, deterministic exercise flow, and fully local resource actions.

- [ ] **Step 1: Improve graph interaction safety.**

`移除节点` opens a confirmation dialog; confirm removes only the node, clears selection, and updates node count. Its related-node buttons must focus an existing node, or show a local unavailable message when the target was removed.

- [ ] **Step 2: Complete exercise navigation semantics.**

```ts
function skipQuestion() {
  if (questionIndex.value === questions.length - 1) finish()
  else { questionIndex.value += 1; answer.value = ''; submitted.value = false }
}
```

`查看全部` expands local history. Feedback buttons navigate with context, and `错题重练` resets only incomplete/wrong question state.

- [ ] **Step 3: Complete resource actions.**

- Export selections display a non-blocking local toast, not `window.alert`.
- Flashcards flip between question and answer; previous/next buttons update the displayed index.
- Project steps expand/collapse local guidance.
- Resource deletion confirmation updates the grid and shows the empty state after the last item.

- [ ] **Step 4: Browser verification.**

Verify graph filter/confirm deletion, all exercise question types and skip behavior, and resource search/filter/modal/flashcard/export/delete states.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/views/KnowledgeGraphPage.vue frontend/src/views/ExerciseCenterPage.vue frontend/src/views/ResourceCenterPage.vue
git commit -m "feat: complete graph exercise and resource controls"
```

## Task 7: Full document-coverage acceptance pass

**Files:**
- Modify only if a browser check exposes a defect in one of the files above.

**Consumes:** All prior tasks.

**Produces:** Verified local demo flow and final build evidence.

- [ ] **Step 1: Build the app.**

Run: `npm run build`

Expected: exit code `0`. Vite dependency/chunk advisory output may remain, but TypeScript and Vite build failures are not acceptable.

- [ ] **Step 2: Run the full browser script.**

```bash
npx --yes --package @playwright/cli playwright-cli -s=final open http://127.0.0.1:5173/
# verify five chat modes and active conversation
# verify sidebar new/rename/delete/persistence
# verify analysis → graph → exercise → resource flow
# verify plan operations and every module modal/dropdown
```

Expected: zero browser console errors and every P0/P1 interaction has a visible result.

- [ ] **Step 3: Capture one screenshot per module and inspect them.**

```bash
npx --yes --package @playwright/cli playwright-cli -s=final screenshot --filename=alignment-final.png
```

Expected: no layout overflow, dead overlays, or style regressions at desktop width.

- [ ] **Step 4: Commit any fixes and report the verification evidence.**

```bash
git add frontend/src/router/index.ts frontend/src/stores/demoConversation.ts frontend/src/views/Home.vue frontend/src/views/QuestionNavChat.vue frontend/src/views/LearningAnalysisPage.vue frontend/src/views/LearningPlanPage.vue frontend/src/views/KnowledgeGraphPage.vue frontend/src/views/ExerciseCenterPage.vue frontend/src/views/ResourceCenterPage.vue
git commit -m "fix: pass design interaction acceptance"
```
