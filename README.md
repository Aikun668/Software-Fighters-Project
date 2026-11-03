# 智学云 DeepTutor

> 基于大模型的个性化资源生成与学习多智能体系统

> **项目重定位说明**：本项目现已转为**个人主导维护的 Agent 工程项目**，主线聚焦 Python 多智能体内核
> （意图门控 → 路由 → 多 Agent 编排 → 质量门 → 流式输出）。Java 业务层与 Vue 全站转为**参照与演示边界**，
> 不再作为维护主线。仓库历史中保留的赛事与多人协作痕迹仅作过程记录，当前设计与实现以本说明为准。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Java-17-orange?logo=openjdk" alt="Java">
  <img src="https://img.shields.io/badge/Vue-3.5-green?logo=vuedotjs" alt="Vue">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Spring_Boot-3.4.6-6DB33F?logo=springboot" alt="Spring Boot">
  <img src="https://img.shields.io/badge/LangGraph-0.4+-purple" alt="LangGraph">
  <img src="https://img.shields.io/badge/ChromaDB-0.6+-white" alt="ChromaDB">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
</p>

---

## 一句话说清

**传统网课给所有人看同样的内容。我们给每个学生生成不同的学习材料、不同的练习题目、不同的学习路径——因为系统通过对话持续了解每个学生的知识水平和学习风格，然后由知识图谱驱动的计划引擎为每个人规划最优的学习顺序和复习节奏。**

---

## 核心创新

知识图谱不是用来展示的，是用来**计算**的。学习计划不是一次生成就完事的，是**动态演化**的。学生画像不是填表填出来的，是**对话中自然提取**的。

```
┌──────────────────────────────────────────────────────────────┐
│                      学生画像（6 维动态）                       │
│  知识基础 · 认知风格 · 学习目标 · 薄弱点 · 学习节奏 · 兴趣方向    │
│         ↑ 对话提取          ↑ 练习反哺          ↑ 计划反馈      │
└────────┬─────────────────────┬─────────────────────┬──────────┘
         │                     │                     │
         ▼                     ▼                     ▼
   ┌──────────┐        ┌──────────────┐        ┌──────────┐
   │  智能答疑  │        │  资源生成(6种) │        │  练习评估  │
   │ RAG+画像  │        │  多Agent协同   │        │  错因分析  │
   └──────────┘        └──────────────┘        └──────────┘
         │                     │                     │
         └─────────┬───────────┴───────────┬────────┘
                   │                       │
                   ▼                       ▼
         ┌────────────────────────────────────────┐
         │            知识图谱（可计算）              │
         │  · 前置门控 → 没掌握前置知识，节点锁住     │
         │  · 路径推断 → BFS+拓扑排序，最优学习顺序   │
         │  · 掌握度热力图 → 5级颜色编码，一目了然    │
         │  · 动态生长 → 对话提取新节点，LLM自动补边  │
         └──────────────┬─────────────────────────┘
                        │
                        ▼
         ┌────────────────────────────────────────┐
         │            学习计划引擎（纯算法）           │
         │  · 半衰期衰减 → mastery *= e^(-0.693·t/h) │
         │  · 软着陆 → 3天继续/7天热身/21天回归检测   │
         │  · 动态重排 → 自动插入间隔复习步骤         │
         │  · 多事件积累 → 看资料+0.1 做对+40% 做错-0.2│
         └────────────────────────────────────────┘
```

---

## 系统架构

```
浏览器 (Vue 3 + Element Plus + Pinia)
       │ HTTP :8080
       ▼
Java SpringBoot 3.4.6 — 业务编排层
  15 个 Controller · 13 个 Entity · 11 个 Service
  认证(JWT) · CRUD · Redis 缓存 · MinIO 文件存储
       │ HTTP :8001（仅内网）
       ▼
Python FastAPI — AI 推理层
  42 个端点 · 20+ Agent · 5 Center · 7 Workflow
  LangGraph 状态图 · ChromaDB 向量库 · 4 通道 LLM
       │
       ▼
  DeepSeek V4 Pro / Flash · Qwen 3.7 Plus / Max
```

**关键设计原则：** Java 负责一切 CRUD，Python 只做 AI 计算。Python 不调 Java，不碰数据库，所有上下文由 Java 在请求体中传入。这就是"Architecture #2"——AI 服务零状态，可独立扩缩。

---

## 功能矩阵

### 对话式学习（统一入口）
| 端点 | 说明 |
|------|------|
| `POST /api/chat` | 统一对话入口，RouterAgent 自动识别意图，分派到 5 个 Center 并行/串行执行，SSE 流式返回 |

### 智能答疑
| 端点 | 说明 |
|------|------|
| `POST /tutor/chat` | RAG 检索增强答疑，读取学生画像调整解释策略，支持多模态（图片 base64/URL）|
| `POST /solve` | 分步解题，含置信度，调查→规划→求解→验证 4 阶段 |

### 资源生成（6 种类型）
| 端点 | 说明 |
|------|------|
| `POST /resources/generate` | Director 路由到 ContentAgent/CodeAgent/MindMapAgent/FlashCardAgent/ProjectAgent/InteractiveDiagramAgent |
| `POST /resources/export-pptx` | 内容块导出 PPTX |
| `POST /resources/export-pdf` | 内容块导出 PDF |

### 练习与评估（完整闭环）
| 端点 | 说明 |
|------|------|
| `POST /exercise/generate` | 按策略出题（薄弱点/错题同类/新题），3 种题型 |
| `POST /exercise/grade` | 选择题精确判分 + 简答题 LLM 关键点评分 + 编程题 3 维度评分 |
| `POST /exercise/error-analysis` | 错因深度分析 |
| `POST /exercise/categorize` | 题目→知识图谱节点匹配 |
| `POST /exercise/session/analyze` | 会话分析，计算掌握度变化 |
| `POST /exercise/profile/enrich` | 练习数据反哺学生画像 |

### 知识图谱（可计算）
| 端点 | 说明 |
|------|------|
| `POST /knowledge-graph/{courseId}` | 带掌握度注入的完整知识图谱 |
| `POST /graph/layered` | BFS 分层布局（前端可视化） |
| `POST /graph/check-prerequisites` | 前置条件门控检查 |
| `POST /graph/next-node` | 基于掌握度的下一个节点推荐 |
| `POST /graph/progress` | 学习进度摘要（按类别/难度分组） |
| `POST /graph/extract` | 从对话中提取新知识节点 |
| `POST /graph/suggest-edges` | LLM 自动建议遗漏的图谱边 |
| `POST /graph/export-mermaid` | Mermaid 流程图导出 |

### 学习计划（动态引擎）
| 端点 | 说明 |
|------|------|
| `POST /plans/create-from-path` | 目标→分解→排程 3 阶段管线生成完整学习计划 |
| `POST /plans/{id}/progress` | 更新步骤进度，计算掌握度变化（半衰期模型） |
| `POST /plans/{id}/status` | 计划状态（软着陆检测 + 遗忘衰减） |
| `POST /plans/{id}/regression-check` | 回归检测：出热身题→判分→重排计划 |
| `POST /plans/{id}/review-schedule` | 间隔重复复习日程生成 |
| `POST /plans/{id}/node-status-change` | 节点状态变更→级联锁解锁后续节点→插入复习步骤 |

### 学生画像（6 维动态）
| 端点 | 说明 |
|------|------|
| `POST /profile/chat` | 对话式画像构建（不是填表，是聊天中自然提取） |
| `GET /profile/status` | 画像完整度检测 |

---

## 技术亮点

### 三道防线防幻觉
1. **输入层** — `SAFETY_SYSTEM_PROMPT` 统一注入所有 Agent，约束领域边界
2. **领域门控** — `DomainRouter` 判断问题是否为 AI 领域，非 AI 问题不查知识库
3. **输出核查** — `@kb_verify` 逐字段比对知识库 + `_postprocess_output` 递归安全扫描

### 计划引擎（纯算法，不调 LLM）
- **动态半衰期：** 基础 3-14 天（按难度），复习次数越多半衰期越长（最高+7天）
- **软着陆：** 空闲 ≤3 天直接继续 / 4-7 天热身题 / 8-21 天回归检测 / >21 天重建路径
- **多事件积累：** 浏览资源 +0.1，练习做对 +40%，做错 -0.2，提问 +0.05
- **动态重排：** 学完节点→自动插入复习步骤→级联解锁后续节点

### 多智能体协作（不是花架子）
- 4 **Center**（Auto/Plan/Resource/Visualization）统一调度 20+ Agent
- `RouterAgent` 双通道意图识别（关键词 + LLM），互斥组去重
- `ResultAgent` 汇总多 Center 结果，去重 + 质量门 + 统一 SSE 输出

### 知识图谱计算层
- **前置门控：** 遍历 `depends_on` 边，逐条判定 mastery ≥ threshold
- **路径推断：** BFS 分层 + 拓扑排序 + 关键路径（DAG 最长路）
- **动态生长：** 对话中提取候选节点 → 用户确认 → LLM 自动补边
- **5 级可视化：** 灰（锁住）→ 琥珀（接触）→ 蓝（学习）→ 绿（掌握）→ 深蓝（精通）

### 可视化管线
- 答疑后自动判断是否需要图解 → `AnalysisAgent` → `CodeGeneratorAgent` → 确定性验证 → `ReviewAgent` 修复
- 支持 Mermaid / SVG / D3.js / Chart.js / HTML

---

## 技术栈

| 层 | 技术 |
|---|------|
| **前端** | Vue 3.5 + TypeScript 6.0 + Element Plus 2.14 + Pinia 3.0 + Vite 8.0 + ECharts 6.1 |
| **主后端** | Spring Boot 3.4.6 + MyBatis-Plus 3.5.9 + Redis + MinIO 8.5.7 + Knife4j 4.5 |
| **AI 微服务** | Python 3.11 + FastAPI + LangGraph 0.4 + LangChain + ChromaDB 0.6 + Pydantic |
| **大模型（4 通道）** | DeepSeek V4 Pro（重推理）· Flash（初筛）· Qwen 3.7 Plus（中）· Max（审查） |
| **数据库** | MySQL 8.0（utf8mb4）+ Redis 7 |
| **LLM 协议** | OpenAI 兼容 HTTP + 星火 WebSocket 双 Provider 策略模式 |

---

## 项目结构

```
Software-Fighters-Project/
├── ai-service/                         # Python AI 微服务（维护主线）
│   ├── app/
│   │   ├── agents/                     # 20+ Agent（tutor/content/code/exercise/solve/path/...）
│   │   │   └── visualize/              #   可视化管线（分析→生成→审查）
│   │   ├── centers/                    # 5 Center（chat/auto/plan/resource/visualization）
│   │   │   └── router_agent.py         #   意图路由（关键词+LLM 双通道）
│   │   ├── services/                   # 13 服务（graph/plan/evaluation/exercise_*/llm/...）
│   │   ├── workflows/                  # 7 Workflow（resource_gen/learning_path/deep_solve/...）
│   │   ├── orchestration/              # Director 路由 + AgentBus 通信 + TurnSummary
│   │   ├── utils/                      # 15 工具（安全/JSON/Prompt/SSE/导出/...）
│   │   └── events/                     # SSE 事件类型定义
│   ├── prompts/                        # 58 个 Prompt YAML 模板（30 目录）
│   ├── tests/                          # 77 个测试文件（单元+压测+验证）
│   ├── data/                           # 知识图谱骨架 + 动态图数据
│   ├── knowledge_docs/                 # 11 篇课程知识文档
│   ├── internal_api/                   # 内部 HTTP 入口包（48 路由，按业务域拆分）
│   │   ├── __init__.py                 #   依赖装配（惰性单例）+ 聚合 router + re-export
│   │   ├── profile.py / resources.py / tutor.py / chat.py / exercise.py
│   │   └── graph.py / plans.py / inquiry.py / eval_api.py / _helpers.py
│   └── main.py                         # FastAPI 启动入口
│
├── backend/                            # Java SpringBoot 业务层（已搁置，仅作参照）
│   ├── src/main/java/com/university/learning/
│   │   ├── controller/                 # 15 个 REST 控制器（50+ 端点）
│   │   ├── service/                    # 11 个 Service 接口 + 实现
│   │   ├── mapper/                     # 13 个 MyBatis-Plus Mapper
│   │   ├── entity/                     # 13 个实体类
│   │   ├── dto/                        # 25 个请求/响应 DTO
│   │   ├── config/                     # 6 个配置类
│   │   ├── utils/                      # 8 个工具类（拦截器/MinIO/正则/...）
│   │   ├── common/                      # 统一响应封装 + 全局异常处理
│   │   └── client/PythonClient.java    # Python 通信客户端（828 行，38 个方法）
│   ├── sql/                            # 4 个 SQL 迁移脚本
│   └── pom.xml
│
├── frontend/                           # Vue 3 前端（已搁置，仅作参照）
│   └── src/
│       ├── views/                      # 11 个页面（Dashboard/Chat/图谱/练习/资源/...）
│       ├── api/                        # 16 个 API 模块（含 SSE 流式解析）
│       ├── stores/                     # 3 个 Pinia Store（user/chat/learning）
│       ├── router/                     # Vue Router 配置
│       └── components/                 # 可复用组件
│
└── docs/                               # 项目文档
```

### 关键数字

| 维度 | 数量 |
|------|------|
| AI 服务端点 | **42** 个 |
| AI Agent | **20+** 个 |
| Prompt 模板 | **58** 个 YAML |
| Java Controller | **15** 个（50+ 端点） |
| 数据库表 | **13** 张 |
| Python 测试 | **77** 个文件 |
| PythonClient 方法 | **38** 个 |
| 前端页面 | **11** 个 |

---

## 快速开始

### 前置要求
- Python 3.11+ · Node.js 20+ · Java 17+ · Maven 3.9+ · MySQL 8.0 · Redis 7

### 1. 克隆项目
```bash
git clone https://github.com/Aikun668/Software-Fighters-Project.git
cd Software-Fighters-Project
```

### 2. 启动 Python AI 微服务
```bash
cd ai-service
pip install -r requirements.txt
cp .env.example .env          # 编辑 .env 填入 LLM API Key
python main.py                 # 启动 → 127.0.0.1:8001
```

### 3. 启动 Java 后端
```bash
cd backend
# 确保 MySQL 已运行，执行 sql/ 目录下的建表脚本
./mvnw spring-boot:run         # 启动 → localhost:8080
```

### 4. 启动前端
```bash
cd showcase-web
pnpm install
pnpm dev                       # 启动 → localhost:5173
```

### 5. 验证
```bash
# 健康检查
curl http://127.0.0.1:8001/health

# 获取知识图谱
curl -X POST http://127.0.0.1:8001/internal/knowledge-graph/ai_course \
  -H "Content-Type: application/json" \
  -d '{"masteries": {"ai_overview": 0.9}}'
```

---

## 分支

| 分支 | 说明 |
|------|------|
| `main` | 稳定主线，已验收的基线 |
| `for-work` | 当前开发分支，日常改动在此进行 |

> 历史分支（`后端改造分支`、`rescue/*`、`archive/*` 等）为早期过程残留，已停止维护，未合并内容见对应分支。

---

## 维护定位

本项目现为**单人维护**，精力集中在 Python 多智能体内核：

| 范围 | 状态 |
|------|------|
| **Python AI 内核**（编排 · 流式 · 质量门 · 状态隔离） | **维护主线** |
| Java SpringBoot 业务层 | 搁置（仅作接口参照，不跟进维护） |
| Vue 3 全站 | 搁置（仅保留编排演示一个展示面） |

---

## 工程改造进展

> 依据 `archive/temp_file/9.15工程改造计划/`（渐进式架构收敛：API 只做协议、每个业务能力只有一个主入口）。
> **阶段 E（取消 / 背压 / 断线重连 / 可观测）按决策跳过** —— 其四项与《学习闭环化五优先级技术路线与实施总纲》P4 逐条对应，并入后续"按需、由真实问题触发"的建设。
> 主线转入 `3、学习闭环化`。当前阶段：**P0 已完成，准备进入 P1**。

| 轮次 | 内容 | 状态 | 验收记录 |
|---|---|---|---|
| 六域收口 | 计划 / 资源 / 练习 / 答疑 / 聊天 / 图谱 各收敛为唯一 Center 入口 | ✅ | `验收记录/*-2026-09-1x.md` |
| 公共设施抽取 | 8 个流式端点的 SSE 样板 + SSRF / 导出路径守卫共享化 | ✅ | `公共设施抽取-2026-09-19.md` |
| 单例装配统一 | 18 个 `_get_xxx` 统一双检锁、声明收拢为单一区块 | ✅ | `单例装配统一-2026-09-20.md` |
| 错误兜底与多模态归位 | `main.py` 全局 500 信封 + 32 处 `exc_info` + 多模态纯函数归位 | ✅ | `错误兜底与多模态归位-2026-09-20.md` |
| **内部接口拆包** | `internal_api.py`（1459 行）→ `internal_api/` 包（11 文件 / 48 路由）；67 条 per-case 响应 sha256 与拆包前一致 | ✅ | `内部接口拆包-2026-09-24.md` |
| **P3-A 路由与命名约定** | 三类决策/命名/状态范围立约定 + 9 模块澄清标注 + 19 例「决策所有权」契约测试（零行为变化，55 条字节存证一致） | ✅ | `P3-A-路由与命名约定-2026-09-24.md` |
| **P3-B1 结构收敛** | 删 `RouterAgent` 死代码 + 画像图节点改名 `completeness_check` + `ResourceWhiteboard` 移出 `workflows/`（结构变、字节不变，55 条存证一致） | ✅ | `P3-B1-结构收敛-2026-09-24.md` |
| **P3-B2 重命名** | `Director`→`ResourceAgentSelector`、`DomainRouter`→`DomainClassifier`（含模块文件与实例属性；结构变、字节不变，55 条存证一致） | ✅ | `P3-B2-重命名-2026-09-24.md` |
| **P3-B3a 状态范围收敛** | 逐请求回调改 `contextvars`（**修掉已复现的并发 token 串流**）+ 节点复用改公开 API + 分发映射表化 + `ResultAgent`→`ChatTaskDispatcher`（零行为变化，55 条存证一致） | ✅ | `P3-B3a-状态范围收敛-2026-09-24.md` |
| **P3-C SSE 伪造帧防护 + 遗留清零** | 补注入契约测试（真实 ASGI 注入伪造 done 帧）→ 证明威胁已由「帧载荷强制 JSON 编码」中和；**`sse_sanitize` 经证据否决接线**；分支遗留 **10/14 终结**：`MM-A09` SVG 绕过**已修**、导出路径包含性**已加固**、计划域基准**日期归一化**、**16 例陈旧/环境依赖红灯清零**（含 `test_sse_heartbeat` 按「包装器即流边界」重写） | ✅ | `SSE伪造帧防护与sse_sanitize接线决策-2026-09-25.md` |
| **P3-B3b 画像单层化** | 双层 LangGraph → 单层：外层 3 节点，`pipeline` 委托 `ProfileAgent.run()`；被静默跳过的 `semantic_judge`（语义去重）/ `audit`（画像审计）**已激活**（**行为变更轮**，含一行回退方案） | ✅ | `P3-B3b-画像单层化-2026-09-25.md` |

| **P3-D 模型参数清洗 + 统一事件层** | ①GUIDE P2 第 3 步收官：3 个漏网 LLM 入口接上 `sanitize_model`（图谱抽取 / 建计划 / 出题）+ `_get_mock_flag` **环境化**；②流式**阶段 B**：新增 `app/events/stream.py`（`run_id` + 单调 `seq` + Collector 对账，**零字节变化**）；③补「真实画像管线」存证 harness（此前被 stub 掩盖） | ✅ | `P3-D-模型参数清洗与统一事件层-2026-09-25.md` |

| **P3-E 流式阶段 C（C1–C5 全部完成）** | ①最小实验量清 LangGraph 1.1.2 能给的流（**关键意外收获**：手工嵌套 `ainvoke` 的内层节点事件可见，不必重写嵌套）；②转换层 `ainvoke_with_events`（等价替换 + 分层节点事件）；③Agent 层接入事件源；④一致性验证（终态/节点覆盖/顺序）；⑤**开关默认开启** + 四个 Workflow 自动获得节点事件。**修掉嵌套开流互相污染的真问题** —— 58 条字节/指纹全一致 | ✅ | `P3-E-流式阶段C-2026-09-25.md` |
| **P3-E 补丁 · Workflow 事件源复用（P0 修复）** | 修掉 `BaseWorkflow.run` 无条件自建 `StreamEmitter` 覆盖上游的断链：资源生成路径的节点事件曾落入**无消费者的局部实例**、`run_id` 与同请求不一致。改为「有上游 → 复用（同一 `run_id`）；无上游 → 自建」；`AI_SERVICE_GRAPH_STREAM=0` 保持**硬总闸**语义。新增契约 `CS-B04`~`CS-B06`。存证：SSE **19/19**、图谱 **27/27**、计划 **9/9** 逐字节一致；画像 3 条**语义一致**（raw-byte 因字段顺序变化，见下条） | ✅ | 本轮（2026-09-26） |
| **P3-E 补丁（续）· P1/P2 全量修复** | ①**P2** `center.*` / `node.*` 事件类型分离（同一类型承载两种载荷 schema 的问题消除）；②**P2** 兜底不再回退 `ainvoke` —— **禁止重跑整张图**（防 LLM/DB 副作用与成本翻倍）；③**P1** `DeepSolveWorkflow` 接入 `BaseWorkflow`（四个流程同构）；④**P1** C4 对账补**真实 Workflow**（`ProfileWorkflow` 生产图 + 内层嵌套 Agent）；⑤**P1** 默认开启代价量化：`CS-A07` 实测大 state（200KB）倍率 **1.13x**。新增契约 `EM-B04` / `GS-A07` / `CS-A05`~`CS-A07` / `DS-A01` | ✅ | 本轮（2026-09-26） |
| **画像存证键序归一化** | review 发现 `deep_solve.py` 接入 `BaseWorkflow` 后画像载荷的 **JSON 字段顺序**变化 → raw-text sha256 全变，但 **84 个事件逐条语义完全相同**。harness 增加 `data:` 载荷 `sort_keys` 归一化（与计划域日期归一化同法），基准重出为 `acceptance/snapshots/profile/_accept_profile_pipeline_after_normalized.txt`；**同规则回放 09-25 旧基准 → 3/3 一致** | ✅ | 本轮（2026-09-26） |
| **阶段 D 最小切片 · 执行进度可见** | 内部 `node.started` / `node.completed` → 线上 `progress` 帧。`node.started` 取自 `debug` 流的 `task` 事件（实测与 `updates` **同形 namespace**，故**不必**逐节点改 `custom` writer）；前端解析器新增 `onProgress`（**绝不进正文**）+ 对话页最简进度行。**用户可见变更轮**：既有帧逐帧不变、只**新增**进度帧。动手前侦察确认 **Java 网关原样透传**新事件类型（`emitter.send(SseEmitter.event().data(eventData))`，其 `type` 分支只用于入库、不过滤）。契约 `PG-A01`~`PG-A05` / `PG-B01` / `GS-A08` | ✅ | `阶段D-执行进度可见-2026-09-26.md` |
| **阶段 D 收口 · 端到端 harness 补盲区** | 新增 `acceptance/harness/chat_progress_frames.py`：**不 stub 任何 Center/Workflow**，跑真实 `POST /internal/api/chat`（ChatCenter → ChatTaskDispatcher → TutorAgent 图），把 `progress` 帧纳入指纹与断言（started/completed 成对、token 正文非空、done 唯一且最后）。实测 **79 帧**（69 token + 6 进度帧）、`progress_stages=['analyze','respond','retrieve']`、两次运行指纹一致。**过程中发现真问题**：聊天链路**未接** `AI_SERVICE_MOCK_LLM` —— 构造 Agent 时不传 mock 旗标（`ChatCenter._get_dispatcher()` 直连 `DecomposeAgent()` 等）、个别处还直接 `OpenAILLM(...)`，故无 Key 环境下整条链路在**构造期**抛错；harness 被迫对 `create_llm` / `OpenAILLM` 做全覆盖 patch（已在记录登记） | ✅ | `阶段D-执行进度可见-2026-09-26.md` |
| **P0 真实链路可信（学习闭环化首个阶段）** | **P0-B**：开关归一到 `AI_SERVICE_MOCK_LLM` 单一真源（`USE_MOCK_LLM` 兼容别名）+ `create_llm`/`OpenAILLM`/`SparkLLM` 改 `None` 语义 + 7 Center / Dispatcher / 2 Agent / 摘要路径全链透传；**P0-A**：真实链路台账；**P0-C**：`chat_progress_frames` **去掉 47 行全覆盖 patch**，新增计划 / 练习两条真链路 harness。**实测**：契约 **34 passed**、针对性回归 **202 passed**、聊天 harness **79 帧零 patch**（与阶段 D 记录一致 ⇒ 行为等价）。过程中修复 **3 处被 patch 掩盖的漏网**（`VisualizePipeline` / `plan_center.ExerciseCenter` / dispatcher 默认 Center） | ✅ | `1、P0-真实链路可信/验收记录/P0-真实链路与模型配置一致性-2026-09-27.md` |

**全量测试**：`1595 passed / 15 skipped / 0 failed`（P3-D 新增 22 例 + P3-E 新增 24 例契约后见验收记录）

**P0/P1/P2 修复轮验证**：事件/流式契约 5 文件 `44 passed`；受影响面 8 文件 `212 passed / 3 skipped`（全量复跑见下）

**本轮全量复跑**（2026-09-26）：`1651 passed / 15 skipped`（`tests/` 口径，收集 **1665** 例）。另根目录 `test_spark_api.py`（`async def test_*` 被 pytest 误收集）与 `test_connectivity.py`（需联网）是**手工脚本**，贡献 `2 failed + 1 error`，与本轮改动无关。

**存证口径（本轮起）**：SSE / 图谱 / 计划 = **逐字节** sha256 一致；画像 = **语义归一化**后一致（`sort_keys` 键序 + `<TS>` 时间戳），基准 `acceptance/snapshots/profile/_accept_profile_pipeline_after_normalized.txt`

**P3-E 修复覆盖**：原 review 清单 ①~⑤ 已全部处理 —— ①→`CS-A05`/`CS-A06`（真实 Workflow 对账）、②→`EM-B04`（center/node 分离）、③→`GS-A07`（抛错不重跑）、④→`CS-A07` 量化（实测 **1.13x**，`CS-A04` 保留防病态退化定位）、⑤→`DS-A01`（DeepSolve 接入基类）

**仍有登记（未做）**：① dispatcher 在 `create_task` 前 `current_emitter.set` 的上下文污染窗口（实际无害）；② ~~节点事件暂无**用户可见**消费者~~ → 阶段 D 已接（**仅对话页**，`conversations.ts` 另一份解析器与其余页面待接）；③ 进度**文案映射表**未做 —— 占位文案直接露内部节点名（`extract` / `merge`）；④ ~~端到端 harness 盲区~~ → **已补**：`acceptance/harness/chat_progress_frames.py`（真实聊天链路，`progress` 帧入指纹）；⑤ 聊天链路未接 `AI_SERVICE_MOCK_LLM`（见上条：构造 Agent 不传旗标 + 直接 `OpenAILLM(...)`）→ 无 Key 环境无法离线跑聊天链路

**下一步**：**进入 P1**（学习状态与学习证据 V1 设计），需先立 `P1-学习状态与学习证据V1设计方案.md`。
**前提（P0-A 台账结论）**：四个学生动作中**只有"答疑"全链贯通**，计划 / 练习 / 资源的**前端第一跳是断的**（页面为静态演示数据）→ P1 的"六类状态样例"只能先用后端 / harness 造数据，**不能假装已有真实学习证据**；这些页面的真实接线属 P3。

---

## 许可证

MIT License

---

<p align="center">
  <b>智学云 DeepTutor</b> — 让每个学生都有一条属于自己的学习路径
</p>
