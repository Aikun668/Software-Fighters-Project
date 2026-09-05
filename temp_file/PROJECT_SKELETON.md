# Software-Fighters 项目骨架与后端对接指南

> **项目**: 第15届中国软件杯 - AI多Agent教育辅导系统  
> **当前分支**: `agent-dev`  
> **文档用途**: 帮助后端团队快速理解项目结构，明确对接边界  
> **版本**: v1.0 (基于2026-06-01代码快照)

---

## 一、宏观架构（一句话总结）

```
前端(Vue3) → Java后端(:8080) → Python AI服务(:8001)
                  ↓
               MySQL + ChromaDB
```

**核心逻辑**: 前端只认Java后端，Java后端转发请求到Python AI服务。AI服务负责所有"智能"逻辑（Agent推理、RAG检索、内容生成），Java后端负责业务数据（用户、课程、学习记录）。

---

## 二、目录骨架（宏观视角）

```
Software-Fighters-Project/
├── frontend/                  # Vue3 前端（已完工，Day 1-3）
│   ├── src/
│   │   ├── views/            # 页面：聊天、学习路径、练习题
│   │   ├── components/       # 组件：消息气泡、思维导图渲染
│   │   └── stores/           # Pinia状态管理
│   └── package.json
│
├── backend/                   # Java SpringBoot 后端（基础框架，待完善）
│   └── src/main/java/com/softwarefighters/
│       ├── controller/       # ★ 只有 AITutorController.java（1个接口）
│       ├── service/          # （空，待后端补充）
│       ├── entity/           # （空，待后端补充）
│       └── config/           # （空，待后端补充）
│
├── ai-service/                # Python FastAPI AI微服务（核心，Day 4-5）
│   ├── main.py               # 服务入口（启动FastAPI）
│   ├── internal_api.py       # ★ 6个API端点（后端对接这里）
│   ├── test_spark_api.py     # LLM连通性测试
│   │
│   ├── app/
│   │   ├── agents/           # 10个Agent实现
│   │   │   ├── base_agent.py        # Agent基类（抽象）
│   │   │   ├── profile_agent.py     # 画像构建Agent
│   │   │   ├── tutor_agent.py       # 智能答疑Agent（RAG）
│   │   │   ├── content_agent.py     # 内容生成Agent
│   │   │   ├── exercise_agent.py    # 练习题生成Agent
│   │   │   ├── path_agent.py        # 学习路径规划Agent
│   │   │   ├── code_agent.py        # 代码示例Agent
│   │   │   ├── flashcard_agent.py   # 闪卡Agent
│   │   │   ├── mindmap_agent.py     # 思维导图Agent
│   │   │   └── reading_agent.py     # 阅读理解Agent
│   │   │
│   │   ├── workflows/        # LangGraph工作流编排
│   │   │   ├── base_workflow.py     # 工作流基类
│   │   │   ├── profile_workflow.py  # 画像对话流程
│   │   │   ├── resource_gen.py      # 资源生成流程（核心）
│   │   │   ├── learning_path.py     # 路径规划流程
│   │   │   └── resource_whiteboard.py
│   │   │
│   │   ├── services/         # 业务服务层
│   │   │   ├── llm_service.py       # LLM调用封装
│   │   │   ├── knowledge_base.py    # RAG知识库
│   │   │   ├── profile_service.py   # 画像读写
│   │   │   └── resource_service.py  # 资源管理
│   │   │
│   │   ├── db/               # 数据库模型和连接
│   │   ├── models/           # Pydantic数据模型
│   │   ├── events/           # SSE事件流工具
│   │   ├── orchestration/    # LangGraph图构建
│   │   └── utils/            # 工具函数
│   │
│   ├── tests/                # 测试用例（93个）
│   ├── chroma_data/          # ChromaDB向量库数据
│   ├── knowledge_base/       # 原始知识文档（10篇Markdown）
│   └── .env                  # 环境变量（API密钥、数据库地址）
│
└── docs/                      # 需求文档和路线图
    ├── 战神项目指导路线图.docx
    ├── 前端战神任务说明书.docx
    └── 后端战神任务说明书.docx
```

---

## 三、AI服务核心：6个API端点（后端对接重点）

AI服务运行在 `http://127.0.0.1:8001`，所有端点以 `/internal` 为前缀。**后端需要把以下端点封装成Java API，供前端调用**。

| 端点 | 方法 | 协议 | 功能 | 后端状态 |
|------|------|------|------|----------|
| `/internal/profile/chat` | POST | SSE | 画像构建对话 | ❌ 未实现 |
| `/internal/tutor/chat` | POST | SSE | 智能答疑（RAG） | ⚠️ 只有转发，无业务逻辑 |
| `/internal/resources/generate` | POST | SSE | 生成学习资源（文档+题+思维导图） | ❌ 未实现 |
| `/internal/exercise/generate` | POST | SSE | 生成练习题 | ❌ 未实现 |
| `/internal/path/{student_id}` | GET | JSON | 学习路径规划 | ❌ 未实现 |
| `/internal/profile/workflow/status` | GET | JSON | 画像完整度查询 | ❌ 未实现 |

> **SSE = Server-Sent Events**，即流式输出。AI逐字返回，前端显示"打字机效果"。

### 当前后端实现现状

后端目前 **只实现了1个端点的空壳** (`AITutorController.java`):

```java
@PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> tutorChat(@RequestBody Map<String, Object> request) {
    return aiClient.post()
            .uri("/tutor/chat")          // ❌ 路径错误！应该是 /internal/tutor/chat
            .bodyValue(request)
            .retrieve()
            .bodyToFlux(String.class);   // ⚠️ 直接透传，无错误处理、无认证、无日志
}
```

**已发现的问题**:
1. 转发路径少了 `/internal` 前缀
2. 没有JWT认证或API Key验证
3. 没有请求日志和限流
4. 没有错误降级（AI服务挂了怎么办？）
5. 其他5个端点完全未实现

---

## 四、5大核心Agent职责（AI服务的"大脑"）

```
用户请求 → internal_api.py → 路由到对应Workflow → 调度Agent → LLM推理 → 返回SSE流
```

| Agent | 职责 | 对应端点 | 是否使用RAG |
|-------|------|----------|-------------|
| **ProfileAgent** | 从对话中提取6维学生画像（知识基础、认知风格、学习目标、薄弱点、学习节奏、兴趣方向） | `/profile/chat` | ❌ |
| **TutorAgent** | 智能答疑。先查ChromaDB知识库，再结合学生画像生成个性化回答 | `/tutor/chat` | ✅ |
| **ContentAgent** | 生成教学内容（章节、代码示例、重点提示） | `/resources/generate` | ✅ |
| **ExerciseAgent** | 生成练习题（选择/填空/编程题），优先针对薄弱点出题 | `/resources/generate` (子流程) | ✅ |
| **PathAgent** | 根据画像生成个性化学习路径（步骤列表 + 概念依赖图谱） | `/path/{id}` | ❌ |

> **RAG = Retrieval-Augmented Generation**，即"检索增强生成"。AI先查知识库，再回答问题，避免幻觉。

### Agent协作流程（以"生成资源"为例）

```
用户: "给我讲讲CNN"
    ↓
/resource_gen.py (Workflow)
    ↓
[步骤1] ContentAgent 生成大纲
    ↓
[步骤2] ContentAgent 逐块生成内容（section → code → callout → mindmap）
    ↓
[步骤3] ExerciseAgent 生成3道配套练习题
    ↓
[步骤4] MindMapAgent 生成知识图谱JSON
    ↓
SSE流返回: progress事件 → content_block事件 → done事件
```

---

## 五、RAG知识库现状

**技术栈**: ChromaDB + 文本分块 + 向量检索

**已加载文档** (10篇，约75KB):

| 文档 | 内容 | 字数 |
|------|------|------|
| 01-intro.md | AI导论与历史 | ~5KB |
| 02-ml-basics.md | 机器学习基础 | ~8KB |
| 03-supervised-learning.md | 监督学习 | ~7KB |
| 04-unsupervised-learning.md | 无监督学习 | ~6KB |
| 05-dl-basics.md | 深度学习基础 | ~9KB |
| 06-nlp.md | 自然语言处理 | ~8KB |
| 07-cv.md | 计算机视觉 | ~7KB |
| 08-rl.md | 强化学习 | ~6KB |
| 09-ethics.md | AI伦理 | ~5KB |
| 10-agent.md | AI Agent系统 | ~7KB |

**覆盖评估**: 约70%覆盖了"AI导论"课程，但缺少：
- CNN/ResNet等具体网络架构详解
- Transformer/BERT/GPT原理
- 实际框架教程（PyTorch/TensorFlow）
- 数学基础（线性代数、概率论）

**对后端的影响**: 知识库在AI服务内部管理，后端不需要关心。但如果要扩展课程，需要把新Markdown放入 `knowledge_base/` 目录并重新索引。

---

## 六、数据流与数据库交互

### 6.1 AI服务读写的表

| 表名 | 操作 | 说明 |
|------|------|------|
| `student_profiles` | 读/写 | AI根据对话自动更新学生画像 |
| `users` | 只读 | 确认用户存在（外键约束） |

### 6.2 AI服务不碰的表（后端负责）

| 表名 | 归属 | 说明 |
|------|------|------|
| `learning_records` | 后端 | 学习记录、观看时长 |
| `resources` | 后端 | 资源元数据（标题、类型、作者） |
| `exercises` | 后端 | 练习题库（如果后端要持久化AI生成的题） |
| `learning_paths` | 后端 | 学习路径实例（哪个学生走了哪条路） |

### 6.3 关键数据格式

**学生画像 (student_profiles)**:
```json
{
    "knowledge_base": 50,           // Integer, 0-100
    "cognitive_style": "visual",    // String: visual/auditory/kinesthetic
    "learning_goal": "掌握深度学习", // String
    "weak_points": ["数学", "Python"], // List<String>
    "learning_pace": "moderate",    // String: slow/moderate/fast
    "interest_direction": ["CV", "NLP"] // List<String>
}
```

**AI服务期望的User表结构**:
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,  -- 或 BIGINT
    student_id VARCHAR(20) UNIQUE,          -- 学号
    username VARCHAR(50) UNIQUE,
    full_name VARCHAR(50),
    email VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255),
    role VARCHAR(20) DEFAULT 'student'
);
```

---

## 七、环境配置与启动顺序

### 7.1 依赖服务

| 服务 | 版本 | 用途 | 端口 |
|------|------|------|------|
| MySQL | 8.0+ | 业务数据 + 画像 | 3306 |
| Python | 3.10+ | AI服务运行环境 | - |
| Node.js | 18+ | 前端构建 | - |
| Java | 17+ | 后端运行 | - |

### 7.2 启动顺序

```bash
# 1. 启动MySQL
sudo systemctl start mysql

# 2. 启动AI服务
cd ai-service
python main.py
# → 监听 http://127.0.0.1:8001

# 3. 启动Java后端
cd backend
./mvnw spring-boot:run
# → 监听 http://localhost:8080

# 4. 启动前端
cd frontend
pnpm dev
# → 监听 http://localhost:5173
```

### 7.3 AI服务关键环境变量 (`.env`)

```bash
# LLM配置（当前使用 MiniMax Token Plan）
LLM_PROVIDER=openai
MINIMAX_BASE_URL=https://api.minimax.cn/v1
MINIMAX_API_KEY=your_minimax_token_plan_key_here
MINIMAX_MODEL_CHAT=MiniMax-M3           # 路由 / 初筛 / 判断 / 轻量生成
MINIMAX_MODEL_REASONER=MiniMax-M3       # 重推理 / 代码 / 图解 / 诊断

# 数据库（必须和后端一致）
DATABASE_URL=mysql+aiomysql://root:123666@localhost:3306/ai_edu

# 向量库
CHROMA_PERSIST_PATH=./chroma_data
CHROMA_COLLECTION=ai_intro

# Mock开关（开发调试用，生产设为false）
USE_MOCK_LLM=false
```

---

## 八、后端团队 TODO 清单（优先级排序）

### 🔴 P0 - 阻塞项目联调

- [ ] **修复AITutorController**：路径改为 `/internal/tutor/chat`
- [ ] **实现画像接口**：`/api/profile/chat` → 转发到 `/internal/profile/chat`
- [ ] **实现资源生成接口**：`/api/resources/generate` → 转发到 `/internal/resources/generate`
- [ ] **实现练习题接口**：`/api/exercise/generate` → 转发到 `/internal/exercise/generate`
- [ ] **实现路径规划接口**：`/api/path/{studentId}` → 转发到 `/internal/path/{studentId}`
- [ ] **实现画像状态查询**：`/api/profile/status` → 转发到 `/internal/profile/workflow/status`

### 🟡 P1 - 生产必需

- [ ] **统一错误处理**：AI服务挂了时返回友好错误（而非500）
- [ ] **请求日志**：记录谁、什么时候、调用了什么AI接口
- [ ] **限流保护**：防止单个用户耗尽 AI API 请求额度（MiniMax Token Plan 有额度限制）
- [ ] **认证中间件**：确认内网白名单 or JWT验证方案

### 🟢 P2 - 体验优化

- [ ] **数据持久化**：AI生成的资源/练习题，后端是否存数据库？
- [ ] **缓存层**：热门问题答案是否缓存（Redis）？
- [ ] **画像管理**：后端是否提供画像查看/手动修改接口？

---

## 九、FAQ（后端常见疑问）

### Q1: 前端直接调AI服务不行吗？为什么要后端转发？
**A**: 三个原因：
1. **安全**：AI服务只监听 `127.0.0.1`，不对外暴露
2. **统一**：前端只认Java API，后端可以做认证、限流、日志
3. **数据**：后端需要记录调用日志、计费、学习分析

### Q2: AI服务挂了怎么办？前端会白屏吗？
**A**: AI服务有降级机制：
- LLM调用失败 → 返回mock内容（兜底回复）
- DB连接失败 → 画像为空dict（继续对话）
- 知识库失败 → 检索为空（纯LLM回答）

但**后端也需要做降级**：如果AI服务完全连不上，返回`{"error": "AI服务暂时不可用"}`，前端展示友好提示。

### Q3: 学生画像存在哪里？后端需要管吗？
**A**: 存在MySQL的 `student_profiles` 表。AI服务自己读写，**后端不需要管更新逻辑**。但后端需要：
1. 确保 `users` 表有对应记录（外键约束）
2. 可以提供画像查看接口（只读）
3. 不要直接修改画像字段（避免和AI冲突）

### Q4: AI生成的内容（资源、练习题）需要存数据库吗？
**A**: 当前AI服务**不存**生成内容，只通过SSE流返回给后端。后端如果需要：
- 持久化 → 自己建表存 `content_blocks` 和 `questions`
- 不持久化 → 直接透传给前端，用完即走

建议先不存，等用户量大了再考虑缓存。

### Q5: SSE流式输出，Java后端怎么转发？
**A**: 用Spring WebFlux的 `WebClient` + `SseEmitter`:

```java
@PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter tutorChat(@RequestBody ChatRequest request) {
    SseEmitter emitter = new SseEmitter(300_000L); // 5分钟超时
    
    aiClient.post()
        .uri("/internal/tutor/chat")
        .bodyValue(request)
        .retrieve()
        .bodyToFlux(String.class)
        .subscribe(
            data -> {
                try { emitter.send(data); }
                catch (Exception e) { emitter.completeWithError(e); }
            },
            error -> emitter.completeWithError(error),
            () -> emitter.complete()
        );
    
    return emitter;
}
```

---

## 十、风险与已知问题

| 问题 | 影响 | 状态 |
|------|------|------|
| 后端只有1个转发接口 | 无法完成画像、资源生成等核心功能 | 🔴 阻塞 |
| AI服务 `.env` 中 Spark API Key 未配置 | 如果使用星火模型会报错 | 🟡 已切换 MiniMax Token Plan |
| 知识库缺少CNN/Transformer深度内容 | RAG回答不够深入 | 🟡 计划补充 |
| 缺少负载均衡 | 单机部署，高并发可能OOM | 🟢 比赛阶段可接受 |
| 无自动化部署脚本 | 每次手动启动3个服务 | 🟢 文档已说明启动顺序 |

---

## 附录：关键文件速查表

| 我想了解... | 看这个文件 |
|-------------|-----------|
| 所有API接口定义 | `API_CONTRACT.md` (项目根目录) |
| AI服务的6个端点实现 | `ai-service/internal_api.py` |
| LLM怎么调用 | `ai-service/app/services/llm_service.py` |
| RAG怎么检索 | `ai-service/app/services/knowledge_base.py` |
| Agent基类和规范 | `ai-service/app/agents/base_agent.py` |
| 资源生成全流程 | `ai-service/app/workflows/resource_gen.py` |
| 学生画像数据结构 | `ai-service/app/models/schemas.py` |
| 数据库表定义 | `ai-service/app/db/models.py` |
| 后端当前实现 | `backend/src/main/java/.../AITutorController.java` |
| 前端页面路由 | `frontend/src/router/index.ts` |

---

**编写日期**: 2026-06-02  
**维护者**: AI服务团队 → 向后端团队交接  
**下一步**: 后端团队根据"TODO清单"实现剩余5个接口，完成后可进行端到端联调。
