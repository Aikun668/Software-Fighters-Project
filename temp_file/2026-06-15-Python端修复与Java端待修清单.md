# Python 端变更总览 + Java 端待修清单

> 分支：`后端改造分支` | 最新提交：`3c18418` | 日期：2026-06-15

---

## 一、本次提交交付了什么

### 1. 知识图谱（全新模块）

14 个端点，覆盖骨架管理、动态节点、图谱分析、可视化。

| 端点 | 做什么 |
|------|--------|
| `POST /knowledge-graph/{course_id}` | 获取完整图谱（骨架 + 用户动态节点），含掌握度染色和 UI 操作按钮 |
| `POST /knowledge-graph/{course_id}/node/{node_id}` | 节点详情卡片（前置/后继/子概念/推荐行动） |
| `POST /graph/extract` | 从对话中提取知识点，中文名自动转拼音 ID，LLM 置信度过滤 ≥0.85 |
| `POST /graph/nodes` | 批量增删节点/边 |
| `POST /graph/masteries` | 基于学习事件（做题/看资源/提问）更新各节点掌握度 |
| `POST /graph/reload` | 管理员热重载骨架 JSON |
| `POST /graph/next-node` | 推荐下一步该学的节点（前置解锁 + 掌握度低的优先） |
| `POST /graph/progress` | 学习进度总览：全局掌握率 + 按分类统计（ML/DL/NLP/LLM） |
| `POST /graph/check-prerequisites` | 检查某节点前置是否满足，返回缺失清单 |
| `POST /graph/nodes/{id}/delete` | 删除动态节点（骨架节点受保护不可删） |
| `POST /graph/nodes/{id}/update` | 更新节点元数据（骨架仅可改 difficulty/category） |
| `POST /graph/suggest-edges` | LLM 自动分析未连接节点对，建议遗漏的依赖关系 |
| `POST /graph/export-mermaid` | 导出 Mermaid flowchart（前端可直接渲染） |
| `POST /graph/layered` | BFS 分层布局数据（前端 DAG 可视化用） |

**核心算法**：拓扑排序、DAG 关键路径（最长路径）、BFS 子图裁剪、余弦相似度语义去重、半衰期遗忘衰减模型。

**数据**：骨架 10 节点 15 条边（AI 导论课程），支持用户动态添加节点/边，重启不丢失（`dynamic_graphs.json`）。

### 2. Centers 多中心架构

`app/centers/` — 对话意图路由引擎，替代 `if-else` 分发逻辑：

| 文件 | 职责 |
|------|------|
| `router_agent.py` | 意图识别 → 路由到对应 Center |
| `auto_center.py` | 通用对话（自动感知意图） |
| `chat_center.py` | 统一聊天入口 |
| `exercise_center.py` | 练习生成调度 |
| `plan_center.py` | 学习计划全链路（目标提取→分解→编排→调整） |
| `resource_center.py` | 学习资源生成调度 |
| `visualization_center.py` | 可视化请求调度 |
| `result_agent.py` | 多 agent 结果聚合 |
| `schemas.py` | `CenterTask` / `CenterResult` 统一协议 |

### 3. 新增 10 个 AI Agent

| Agent | 功能 |
|-------|------|
| `GoalAgent` | 从自然语言提取结构化学习目标（标题/知识点/难度等级/截止日期/动机） |
| `DecomposeAgent` | 将学习目标分解为宏观主题 + 微观技能 + 前置知识 |
| `ScheduleAgent` | 根据目标 + 分解结果生成分天学习计划（含里程碑） |
| `AdjustmentAgent` | 基于掌握度 + 遗忘曲线动态调整计划（插入复习/重排顺序） |
| `DiagnoseAgent` | 诊断学生薄弱环节 |
| `ExerciseVariantAgent` | 对已有题目生成变体（改数字/改上下文/改措辞/提升难度） |
| `ImageAgent` | 为知识点生成文生图提示词（DALL·E/Stable Diffusion 可直接用） |
| `LayeredExplainAgent` | 多层次讲解（从直观到严谨自适应） |
| `ProjectAgent` | 项目式学习任务生成 |
| `ReflectionAgent` | 学习反思引导 |

### 4. 其他改进

- **知识提取管道**：对话 → LLM 提取知识点 → 验证/去重 → 返回结构化节点
- **向量嵌入**：BGE 中文嵌入模型，支持 HuggingFace 镜像（`HF_ENDPOINT` 环境变量）
- **PDF 导出**：`pdf_exporter.py` 将内容块渲染为 PDF
- **Deep Solve 增强**：调查→规划→求解→验证 四阶段流水线
- **意图提取增强**：`intent_extractor.py` 从 ~200 行扩展到 ~500 行，支持 14 种意图
- **Event 类型扩展**：新增 `CENTER_START/CENTER_END/INQUIRY` SSE 事件类型

---

## 二、Python ↔ Java 端点契约状态

✅ = 已匹配　❌ = 需 Java 改　⚪ = 端点尚未开发

| Java 方法 | Python 端点 | 状态 | 问题 |
|-----------|------------|------|------|
| `unifiedChatStream` | `POST /api/chat` | ✅ | |
| `buildProfileStream` | `POST /profile/chat` | ✅ | |
| `generateResourcesStream` | `POST /resources/generate` | ✅ | |
| `tutorChatStream` | `POST /tutor/chat` | ✅ | |
| `generateExercisesStream` | `POST /exercise/generate` | ✅ | |
| `gradeExercise` | `POST /exercise/grade` | ✅ | |
| `getEvaluationReport` | `POST /evaluation/report` | ✅ | |
| `exportPptx` | `POST /resources/export-pptx` | ✅ | |
| `solveStream` | `POST /solve` | ✅ | |
| `getKnowledgeGraph` | `POST /knowledge-graph/{id}` | ✅ | |
| `getNodeCard` | `POST /knowledge-graph/{id}/node/{id}` | ✅ | |
| `createPlanFromPath` | `POST /plans/create-from-path` | ✅ | |
| `inquiryResolveStream` | `POST /inquiry/resolve` | ✅ | |
| `errorAnalysis` | `POST /exercise/error-analysis` | ✅ | |
| `getPlanStatus` | `POST /plans/{id}/status` + `/plans/status` | ✅ | 已加兼容路由 |
| `getProfileStatus` | `POST /profile/workflow/status` | ❌ | Java 用 GET，Python 用 POST |
| `getLearningPath` | `POST /path/{student_id}` | ❌ | Java 用 GET，Python 用 POST |
| `getReviewSchedule` | `POST /plans/{id}/review-schedule` | ❌ | Java 用 GET+query 参数，Python 用 POST+body |
| `getConversationSummary` | `POST /conversations/{id}/summary` | ❌ | Java 用 GET+query 参数，Python 用 POST+body |
| `regressionCheck` | `POST /plans/{id}/regression-check` | 🟡 | 路径匹配，但 Java 只传 `{user_id, answers}`，缺 `{plan, steps, days_idle}` |
| `getUserDashboard` | 不存在 | ⚪ | 练习模块 Phase C 开发 |
| `endConversation` | 不存在 | ⚪ | 待确定需求 |

---

## 三、Java 端需修改（按优先级）

**P0 — 立即**：4 个 HTTP 方法错误，调用即 405。

| 方法 | 改什么 |
|------|--------|
| `getProfileStatus` | GET → POST，body 传 `{user_id, student_profile}` |
| `getLearningPath` | GET → POST，body 传 `{user_id, topic, student_profile}` |
| `getReviewSchedule` | GET → POST，query 参数改为 body `{steps, days_ahead}` |
| `getConversationSummary` | GET → POST，query 参数改为 body `{messages, course_id}` |

**P1 — 本周**：`regressionCheck` 补传 `plan`、`steps`、`days_idle` 三个字段。目前不传不会 500，但返回 404。

**P2 — 后续**：`getUserDashboard` 和 `endConversation` 随功能迭代逐步实现。

---

## 四、Python 新增模块位置速查

```
ai-service/app/
├── agents/          # 19 个 agent（新增 10 个）
├── centers/         # 多中心路由引擎（全新模块）
├── services/
│   ├── graph_service.py       # 知识图谱核心（~1040 行）
│   └── knowledge_extraction.py # 知识提取管道（~270 行）
├── api/models.py    # +15 个图谱相关请求模型
└── utils/
    ├── graph_id.py  # 节点 ID 标准化（独立模块，解耦循环导入）
    └── embeddings.py # +语义相似度 + HF 镜像
```

---

*此文档由 AI Agent 根据 `3c18418` 提交生成，供 Java 后端同学对接参考。*
