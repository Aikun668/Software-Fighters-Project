# 智学云 DeepTutor

> 第 15 届中国软件杯 · 基于大模型的个性化资源生成与学习多智能体系统

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
├── ai-service/                         # Python AI 微服务 [队长]
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
├── backend/                            # Java SpringBoot 业务层 [后端]
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
├── frontend/                           # Vue 3 前端 [前端]
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
cd frontend
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

| 分支 | 负责人 | 说明 |
|------|--------|------|
| `main` | 队长 | 主分支，最终合并 |
| `agent-dev` | 队长 | Python AI Agent 开发 |
| `backend-dev` | 后端 | Java SpringBoot 开发 |
| `frontend-dev` | 前端 | Vue 3 开发 |

---

## 团队

| 角色 | 职责 |
|------|------|
| **队长** | Python 多智能体核心 · LangGraph 编排 · 知识图谱 · 计划引擎 · 安全防护 |
| **后端** | Java SpringBoot · MyBatis-Plus · Redis · MinIO · PythonClient 通信层 |
| **前端** | Vue 3 页面 · SSE 流式渲染 · ECharts 知识图谱可视化 · Markdown/Mermaid 渲染 |

---

## 工程改造进展

> 依据 `temp_file/9.15工程改造计划/`（渐进式架构收敛：API 只做协议、每个业务能力只有一个主入口）。当前阶段：**编排解耦（P2 收尾）**。

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

**全量测试**：`1588 passed / 15 skipped / 0 failed`（此前 16 例红灯已全部终结）

**下一步**：P3-B3b（合并双层图 —— **需先确认 `ProfileAgent` 的 `semantic_judge` / `audit` 是否执行**）→ 模型参数清洗（GUIDE P2 step 3）→ 「2、后续流式事件化」。

---

## 许可证

MIT License

---

<p align="center">
  <b>智学云 DeepTutor</b> — 让每个学生都有一条属于自己的学习路径
</p>
