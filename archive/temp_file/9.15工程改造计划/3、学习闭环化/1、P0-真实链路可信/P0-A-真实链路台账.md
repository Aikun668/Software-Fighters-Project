# P0-A 真实链路台账

> **依据**：《学习闭环化五优先级技术路线与实施总纲》§3.3 P0-A。
> **口径**：以**学生动作**为单位逐列追到代码；**禁止**凭接口名、目录名或旧文档推断。
> **核对时间**：2026-09-27。**行号以核对时工作区为准**，重构后会漂移 —— 结论以**函数名 / 端点路径**为锚。
> **方法**：读代码（前端 `views`+`api`、Java `controller`+`PythonClient`、Python `internal_api`+`centers`）+ 跑既有测试/harness 取证。

## 一、状态定义

| 状态 | 含义 |
| --- | --- |
| **已实测** | 有运行证据（测试或 harness 直接打到该段） |
| **只读到代码** | 代码路径存在，但未见运行证据 |
| **未接通** | 某一段缺失，或该段是前端静态演示数据 |

## 二、四个学生动作

### 动作 1 · 发起普通答疑

| 列 | 结论 |
| --- | --- |
| 前端入口 | `views/QuestionNavChat.vue:74` `send()` → `api/chat.ts:10` `sendMessageStream` → `POST /api/chat`（`chat.ts:22`）；路由 `/question-nav-chat` |
| Java 入口/持久化 | `ChatController.java:42` `@RequestMapping("/api/chat")`，`:58` `chat()`。写入：`messages`(`:69`/`:206`)、`conversations`(`:112/116`)、`resources`(`:295/312`)、`learning_plans`+`plan_steps`(`:400/433`)、`student_profiles`(`:522`) |
| Python 业务入口 | `PythonClient.java:45` `unifiedChatStream` → `/api/chat`；`internal_api/chat.py:17` `unified_chat` → `ChatCenter.stream_chat`（`chat_center.py:285`）→ `TutorAgent`；装配点 `internal_api/__init__.py::_get_chat_center` |
| 结果去向 | done 事件回 Java：`saveAiResponse`→`messages`、`saveGeneratedContent`→`resources`、`saveResearchPlan`→计划、`saveProfileDelta`→`student_profiles` |
| **证据状态** | Python 段 **已实测**（`test_chat_center_api_delegation.py`、`test_tutor_center_api_contract.py`）；前端段 **只读到代码**（spec 用 `vi.mock('@/api/chat')` 桩替代 SSE）；Java 段 **只读到代码** |

> 旁路：`internal_api/tutor.py` `POST /tutor/chat` 是独立答疑路由，但 `PythonClient.tutorChatStream` **无 Controller 调用** → `未接通`（死路径）。

### 动作 2 · 完成计划任务

| 列 | 结论 |
| --- | --- |
| 前端入口 | `views/LearningPlanPage.vue`（`/learning-path`）。`:23` `toggleTask` **只改本地数组**；`:15-20` `tasks` 硬编码 → 无 API 调用。`api/plans.ts` 的 `changeNodeStatus`/`updatePlanStep`/`addPlanStep` **无页面引用** |
| Java 入口/持久化 | `LearningPlanController.java`：`POST /api/plans/{planId}/complete-step`、`POST /api/plans/{planId}/progress`、`PUT /api/plan-steps/{stepId}`、`onNodeStatusChange`。写入 `plan_steps`、`learning_plans` |
| Python 业务入口 | `PythonClient.java:519` `completePlanStep` → `/plans/{id}/complete-step`；`:545` `updatePlanProgress` → `/plans/{id}/progress`。路由 `internal_api/plans.py:82` → `PlanCenter.complete_step`；`plans.py:124` → `PlanCenter.update_progress` |
| 结果去向 | 返回 `questions`/`recommended_action`/掌握度变化，Java **仅 `Result.ok` 透传、不落库** |
| **证据状态** | 前端段 **未接通**；Python 段 **已实测**（`test_plan_endpoints_api_delegation.py`）；Java 段 **只读到代码** |

### 动作 3 · 完成练习

| 列 | 结论 |
| --- | --- |
| 前端入口 | `views/ExerciseCenterPage.vue`（`/exercise`）。`:12` `submit()` **只置 `submitted=true`**；`:8` `sets`、`:9` `questions` 硬编码；`:21`/`:23` 写死分数与掌握度变化 → 无 API 调用。`api/exercise.ts:23` `gradeExercise` **无页面引用** |
| Java 入口/持久化 | `ExerciseController.java:30` `@RequestMapping("/api/exercise")`：`POST /grade`(`:71`)、`POST /generate`(`:47`)。写入 `learning_records`(`:238`，仅当带 `resource_id`)、`resources`(`:277`) |
| Python 业务入口 | `PythonClient.java:195` `gradeExercise` → `/exercise/grade`；`:145` `generateExercisesStream` → `/exercise/generate`。路由 `internal_api/exercise.py:77` → `ExerciseCenter.grade`；`exercise.py:27` → `ExerciseCenter.generate_stream` |
| 结果去向 | `grade` 返回 `{correct, feedback/score}`；Java 在带 `resource_id` 时写 `learning_records`（score/progress）；`generate` 的 done `questions` → `resources` |
| **证据状态** | 前端段 **未接通**（提交仅切本地布尔）；Python 段 **已实测**（`test_exercise_center_api_delegation.py`）；Java 段 **只读到代码** |

### 动作 4 · 使用学习资源

| 列 | 结论 |
| --- | --- |
| 前端入口 | `views/ResourceCenterPage.vue`（`/resource-center`）。`:8` `resources` 硬编码；`:11` `exportResource` = `window.alert('演示模式…')` → 无 API 调用。`api/resources.ts` 的 `getMyResources`/`getResourcesByType`/`getResourceDetail` **无页面引用** |
| Java 入口/持久化 | `ResourceController.java:28` `@RequestMapping("/api/resources")`：`GET /list`、`GET /list/{type}`、`GET /{resourceId}`。写入 `resources`（随 `/generate`） |
| Python 业务入口 | `PythonClient.java:91` `generateResourcesStream` → `/resources/generate`；`internal_api/resources.py:26` → `ResourceCenter.stream_generate`。**浏览/详情不经过 Python**（Java 直接读库） |
| 结果去向 | `/generate` 的 done `content_blocks` → `resources` 表；浏览接口直接返回 `Resource` 实体 |
| **证据状态** | 前端段 **未接通**（静态列表 + 导出为演示提示）；Python 段 **已实测**（`test_resource_center_api_contract.py`）；Java 段 **只读到代码** |

## 三、疑似静态演示数据清单

**已被路由的可见页面（高危 —— 学生真的会看到）：**

| 文件 | 硬编码内容 |
| --- | --- |
| `views/ExerciseCenterPage.vue` | `:8` `sets`、`:9` `questions`（题目/选项/正确项/分值）；`:21` 写死「23 / 26 分」「掌握度 45%→61%」；`:23` 写死「55%→72%」与假「AI 批改反馈」 |
| `views/LearningPlanPage.vue` | `:15-20` `tasks`；`:38-40` 计划菜单（65%/30%/10%）；时间线与学情洞察文本写死 |
| `views/ResourceCenterPage.vue` | `:8` `resources`；`:11` 导出 `alert('演示模式…')`；`:15` 弹窗内明写「静态演示资料」「fake-content」 |
| `views/KnowledgeGraphPage.vue` | `:8` `nodes`（掌握度 78/42/68… 全写死） |
| `views/LearningAnalysisPage.vue` | `:14` `dimensions`、`:23` `statItems`、`:33` `heatmap` |
| `views/Home.vue` | `:28` `conversations`、`:34` `navItems` |

**未被路由的死页面（仍含演示数据）**：`ExercisePage.vue`、`LearningPath.vue`、`ResourceCenter.vue`、`Dashboard.vue`、`ProfileChat.vue`、`AITutor.vue` 等。

## 四、结论（进入 P1 的判断）

1. **只有「发起普通答疑」在代码层面全链贯通**（页面→Java→Python→回写 5 张表）；计划 / 练习 / 资源三个动作的**前端第一跳是断的** —— 对应 `api/*.ts` 函数存在但**无人调用**，后端链路齐全却接不上学生操作。
2. **全链只有 Python 段有运行证据**；前端段（spec 用 mock 替代 SSE 客户端）与 Java 段（后端无自动化测试，仅有空壳 `LearningPlatformApplicationTests`）均为 `只读到代码`。
3. **违背总纲 §2.1 的风险已具体化**：总纲担心的"页面静态数据冒充闭环"**确实存在**，且集中在 P3 要处理的三个页面。
4. 对 P1 的含义：`LearningSnapshot` 的 `mastery` / `active_plan` 若要可追溯，**当前没有前端产生的真实学习证据**（计划/练习/资源的真实动作一个都没接通）→ P1 的"六类状态样例"只能先用后端/ harness 造数据，**这一点必须如实登记，不能假装已有真实证据**。
5. 对 P3 的含义：三个页面各需要"一个页面、一条真实链路"的替换，且**不能**把现有静态分数当作学习事实。
