# AI 服务 — 后端对接文档

> **版本**: v2.0 | **日期**: 2026-06-05 | **维护**: AI Agent 组（队长）
>
> **适用对象**: Java SpringBoot 后端开发工程师
>
> **架构**: `前端(Vue3) → Java后端(:8080) → Python AI服务(:8001) → MySQL + ChromaDB`
>
> AI 服务只监听 `127.0.0.1:8001`，不对外暴露。后端负责认证、转发、业务数据管理。

---

## 一、AI 服务接口总览（22 个内部端点）

所有端点前缀为 `/internal`。后端需要逐一封装为对外 API（前缀 `/api`）。

### 1.1 SSE 流式端点（7 个）

| # | 端点 | 功能 | 转发要点 |
|---|------|------|----------|
| 1 | `POST /internal/profile/chat` | 对话式画像构建 | `SseEmitter` 5min 超时，透传 SSE 事件 |
| 2 | `POST /internal/tutor/chat` | 智能答疑（RAG + 多模态） | 支持图片 base64/URL，返回 `conversation_id` |
| 3 | `POST /internal/resources/generate` | 生成学习资源 | 进度事件 + 内容块 + 题目 |
| 4 | `POST /internal/exercise/generate` | 生成练习题 | 支持 warmup 模式 |
| 5 | `POST /internal/solve` | 分步解题 | 返回 `steps` + `confidence` |
| 6 | `POST /internal/api/chat` | 统一聊天（意图路由） | 自动分发到上述端点 |

### 1.2 JSON 端点（15 个）

| # | 端点 | 功能 |
|---|------|------|
| 7 | `GET /internal/path/{student_id}` | 学习路径 + 概念图谱 |
| 8 | `GET /internal/profile/workflow/status` | 画像完整度查询 |
| 9 | `POST /internal/exercise/grade` | 题目评分（选择/简答） |
| 10 | `POST /internal/exercise/error-analysis` | 错题深度分析 |
| 11 | `POST /internal/evaluation/report` | 评估报告生成 |
| 12 | `POST /internal/resources/export-pptx` | 导出 PPTX |
| 13 | `GET /internal/resources/download-pptx` | 下载 PPTX 文件 |
| 14 | `GET /internal/knowledge-graph/{course_id}` | 知识图谱（含用户掌握度） |
| 15 | `GET /internal/knowledge-graph/{course_id}/node/{node_id}` | 节点详情卡片 |
| 16 | `POST /internal/plans/create` | 创建学习计划 |
| 17 | `GET /internal/plans/{plan_id}/status` | 计划状态 + 软着陆 |
| 18 | `POST /internal/plans/{plan_id}/progress` | 更新步骤进度 |
| 19 | `POST /internal/plans/{plan_id}/resume` | 恢复暂停计划 |
| 20 | `POST /internal/plans/{plan_id}/regression-check` | 回归检测（两阶段） |
| 21 | `GET /internal/plans/{plan_id}/review-schedule` | 复习日程 |
| 22 | `POST /internal/plans/{plan_id}/node-status-change` | 节点状态变化联动 |

---

## 二、SSE 流式转发实现

### 2.1 SpringBoot 转发模板

```java
@RestController
@RequestMapping("/api")
public class AIController {

    private final WebClient aiClient = WebClient.create("http://127.0.0.1:8001");

    // ── SSE 流式转发 ──
    @PostMapping(value = "/tutor/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter tutorChat(@RequestBody TutorChatRequest request) {
        SseEmitter emitter = new SseEmitter(300_000L); // 5 分钟超时

        aiClient.post()
            .uri("/internal/tutor/chat")
            .bodyValue(request)
            .retrieve()
            .bodyToFlux(String.class)
            .subscribe(
                data -> {
                    try {
                        emitter.send(SseEmitter.event().data(data));
                    } catch (IOException e) {
                        emitter.completeWithError(e);
                    }
                },
                error -> {
                    // AI 服务挂了 → 返回友好错误给前端
                    try {
                        emitter.send(SseEmitter.event()
                            .data("{\"type\":\"error\",\"content\":\"AI服务暂时不可用\"}"));
                    } catch (IOException ignored) {}
                    emitter.complete();
                },
                () -> emitter.complete()
            );

        return emitter;
    }

    // ── JSON 转发（非流式） ──
    @PostMapping("/exercise/grade")
    public ResponseEntity<?> gradeExercise(@RequestBody GradeRequest request) {
        try {
            Map<String, Object> result = aiClient.post()
                .uri("/internal/exercise/grade")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(Map.class)
                .block(Duration.ofSeconds(30));
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.status(502)
                .body(Map.of("error", "AI服务暂时不可用"));
        }
    }
}
```

### 2.2 转发注意事项

- **路径前缀**: AI 服务所有端点在 `/internal/` 下，转发时不要漏掉
- **超时时间**: SSE 流式接口建议 300 秒（5 分钟），JSON 接口 30 秒
- **错误降级**: AI 服务不可用时返回 `502 Bad Gateway` + 友好提示，不要返回 500
- **请求体透传**: 后端一般不需要修改请求体，直接转发即可（`user_id` 可以通过 JWT 注入）
- **Content-Type**: SSE 接口必须 `produces = MediaType.TEXT_EVENT_STREAM_VALUE`

---

## 三、数据库交互边界

### 3.1 AI 服务管理的表（后端不要写）

| 表 | AI 操作 | 说明 |
|----|---------|------|
| `student_profiles` | **读写** | AI 自动 upsert 画像，后端只读展示 |
| `node_mastery` | **读写** | AI 自动更新知识点掌握度 |
| `learning_plans` | **读写** | AI 创建/更新学习计划 |
| `plan_steps` | **读写** | AI 管理计划步骤 |
| `conversations` | **读写** | AI 管理答疑会话历史 |
| `messages` | **写** | AI 持久化对话消息 |
| `resources` | **写** | AI 记录生成的资源元数据 |

### 3.2 后端管理的表（AI 不碰）

| 表 | 后端操作 | 说明 |
|----|----------|------|
| `users` | **读写** | 用户注册/登录/管理。AI 只读确认外键存在 |
| `learning_records` | **读写** | 学习行为记录（时长、进度等） |
| 自定义业务表 | **读写** | 课程、班级、权限等业务数据 |

### 3.3 AI 服务期望的 users 表结构

```sql
CREATE TABLE users (
    id           INTEGER PRIMARY KEY AUTO_INCREMENT,  -- 或 BIGINT
    student_id   VARCHAR(20) UNIQUE NOT NULL,         -- 学号
    username     VARCHAR(50) UNIQUE NOT NULL,
    full_name    VARCHAR(50) NOT NULL,
    email        VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role         VARCHAR(20) DEFAULT 'student',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**⚠️ 关键**: `student_profiles.user_id` 是 `users.id` 的外键。如果 user 表字段不一致，画像功能无法工作。

---

## 四、AI 服务环境配置

### 4.1 环境变量 (`.env`)

```bash
# LLM 配置
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_MODEL=deepseek-v4-pro

# 数据库（与后端共用 MySQL）
DATABASE_URL=mysql+aiomysql://root:123666@localhost:3306/ai_edu

# ChromaDB 向量库（AI 服务本地）
CHROMA_PERSIST_PATH=./chroma_data
CHROMA_COLLECTION=ai_intro

# Mock 开关（开发调试用，生产设为 false）
USE_MOCK_LLM=false
```

### 4.2 启动顺序

```bash
# 1. MySQL
sudo systemctl start mysql

# 2. Python AI 服务
cd ai-service
pip install -r requirements.txt
python main.py           # 监听 http://127.0.0.1:8001

# 3. Java 后端
cd backend
./mvnw spring-boot:run   # 监听 http://localhost:8080

# 4. 前端
cd frontend
pnpm dev                  # 监听 http://localhost:5173
```

### 4.3 健康检查

```bash
curl http://127.0.0.1:8001/health
# {"status": "ok", "db": "connected"}     ← 一切正常
# {"status": "degraded", "db": "unreachable"}  ← DB 不通，但服务仍可用（降级模式）
```

---

## 五、AI 服务架构概览

### 5.1 服务层

```
internal_api.py (FastAPI Router)
    ├── ProfileWorkflow      → ProfileAgent (画像提取 + 合并 + 审计)
    ├── ResourceGenWorkflow  → ContentAgent + ExerciseAgent + MindMapAgent + ...
    ├── LearningPathWorkflow → PathAgent (路径规划 + LLM 自审)
    ├── GraphService         → 知识图谱加载/校验/掌握度注入/卡片生成
    ├── PlanService          → 半衰期/软着陆/重排/复习日程/联动 (纯算法，无 LLM)
    ├── ConversationService  → 会话持久化/历史加载/长对话压缩
    ├── ProfileService       → 画像读写/增量更新
    ├── KnowledgeBase        → ChromaDB 向量检索
    ├── IntentExtractor      → 自然语言意图识别 (关键词 + LLM 双通道)
    ├── HallucinationGuard   → LLM 输出幻觉检测 (KB 覆盖率验证)
    └── solve_agent.py       → SolveAgent (逐步解题 + 置信度)
```

### 5.2 Agent 列表（13 个，全部基于 LangGraph StateGraph）

| Agent | 功能 | 使用 RAG |
|-------|------|----------|
| ProfileAgent | 对话式画像构建（6 维 + entries 条目模型） | ❌ |
| TutorAgent | 智能答疑（多模态图片 + 幻觉检测 + 类比库） | ✅ |
| ContentAgent | 教学内容分块生成（section/code/callout） | ✅ |
| ExerciseAgent | 个性化出题（warmup 热身 + 回归检测） | ✅ |
| CodeAgent | 代码案例生成 | ❌ |
| MindMapAgent | 思维导图 + Mermaid 图谱 | ❌ |
| FlashCardAgent | 记忆闪卡生成 | ❌ |
| PathAgent | 学习路径规划 + LLM 自审 | ❌ |
| SolveAgent | 分步解题 + 置信度 | ❌ |
| ReadingAgent | 拓展阅读推荐（含来源引用） | ✅ |
| AnalysisAgent | 可视化需求判断 | ❌ |
| CodeGeneratorAgent | 可视化代码生成 | ❌ |
| ReviewAgent | 生成代码审核优化 | ❌ |

### 5.3 数据库表（9 张）

| 表 | 用途 |
|----|------|
| `users` | 用户基础信息 |
| `student_profiles` | 6 维学生画像 + entries 条目 + 审计元数据 |
| `conversations` | 答疑会话 |
| `messages` | 对话消息历史 |
| `resources` | 生成的资源元数据 |
| `learning_records` | 学习进度记录 |
| `learning_plans` | 学习计划 |
| `plan_steps` | 计划步骤（含掌握度/遗忘/复习） |
| `node_mastery` | 知识图谱节点掌握度 |

---

## 六、关键对接流程

### 6.1 新用户引导流程

```
1. 前端 → GET /api/profile/status
   后端转发 → GET /internal/profile/workflow/status?user_id=1
   → 返回 { is_complete: false, filled_dimensions: 0 }
   
2. 前端 → POST /api/profile/chat (SSE)
   后端转发 → POST /internal/profile/chat
   → 多轮对话，画像逐步完善
   → 每轮 SSE 返回 profile_update 事件
   
3. 画像完成 → GET /api/path/1
   后端转发 → GET /internal/path/1
   → 返回学习路径 steps + concept_graph
```

### 6.2 学习流程

```
1. 选择知识点 → POST /api/resources/generate (SSE)
   后端转发 → POST /internal/resources/generate
   → 流式返回 content_blocks + questions
   
2. 学习中有疑问 → POST /api/tutor/chat (SSE)
   后端转发 → POST /internal/tutor/chat
   → 首次返回 meta 事件含 conversation_id
   → 后续带上 conversation_id
   
3. 做练习题 → POST /api/exercise/grade
   后端转发 → POST /internal/exercise/grade
   → 即时评分反馈
```

### 6.3 中断回归流程（软着陆）

```
1. 用户回归 → GET /api/plans/{id}/status
   后端转发 → GET /internal/plans/{id}/status
   → 返回 soft_landing { strategy, message, review_nodes }
   
2. strategy == "regression_check":
   前端 → POST /api/plans/{id}/regression-check
   阶段1 (无 answers) → AI 出题检测遗忘知识点
   阶段2 (带 answers) → AI 判分 + 重排学习计划
```

---

## 七、请求/响应格式规范

### 7.1 AI 服务统一响应格式

**成功**:
```json
{
  "success": true,
  "data": { ... }
}
```

**错误**:
```json
{
  "success": false,
  "errorCode": "NOT_FOUND",
  "error": "计划不存在",
  "details": null
}
```

### 7.2 错误码

| ErrorCode | HTTP 状态码 | 含义 |
|-----------|-------------|------|
| `INVALID_REQUEST` | 400 | 请求参数不合法 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `MISSING_REQUIRED_FIELD` | 422 | 缺少必填字段 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
| `GENERATION_FAILED` | 502 | 内容生成失败 |
| `PERSIST_FAILED` | 500 | 数据持久化失败 |

### 7.3 SSE 事件通用格式

```
data: {"type": "<事件类型>", ...}\n\n
```

| type | 含义 |
|------|------|
| `token` | 逐字文本 |
| `progress` | 进度更新 (含 `stage`, `progress` 0.0-1.0) |
| `meta` | 元信息 (含 `conversation_id`) |
| `profile_update` | 画像更新 |
| `profile_complete` | 画像完成 |
| `stage_start` / `stage_end` | 阶段开始/结束 |
| `content_block` | 内容块 |
| `steps` | 解题步骤 |
| `confidence` | 置信度评分 |
| `done` | 流结束 |
| `error` | 可恢复错误 |

---

## 八、后端 TODO 清单

### P0 — 阻塞联调

- [ ] 实现 22 个 API 端点的转发 Controller（见第一节清单）
- [ ] SSE 接口使用 `SseEmitter` + `WebClient` 透传（见第二节模板）
- [ ] 确认 `users` 表结构与 AI 服务一致
- [ ] 确认 `DATABASE_URL` 指向同一 MySQL 实例
- [ ] AI 服务健康检查集成到后端启动流程

### P1 — 生产必需

- [ ] 统一错误处理：AI 不可用时返回 `502` + 友好提示
- [ ] 请求日志：记录调用者、时间、端点、耗时
- [ ] 限流保护：防止单个用户刷爆 DeepSeek API
- [ ] 认证方案：JWT 验证中间件（或先内网白名单）

### P2 — 体验优化

- [ ] AI 生成内容持久化（存 content_blocks 和 questions 到业务表）
- [ ] 热门问题缓存（Redis）
- [ ] 画像管理后台（只读查看 + 手动重置）

---

## 九、已知风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| DeepSeek API 速率限制 | 高并发时请求排队 | AI 服务内置 mock 降级，后端加限流 |
| ChromaDB 内存占用 | 大知识库 OOM | 当前知识库仅 75KB，影响小 |
| SSE 长连接资源占用 | 大量用户时 Tomcat 线程耗尽 | 使用 WebFlux 异步模型 |
| MySQL 慢查询 | 画像频繁读写 | 画像 update 已有 last_activity_at 索引 |

---

> **维护者**: AI Agent 组（队长）  
> **最后更新**: 2026-06-05  
> **参考**: `temp_file/API_CONTRACT.md` / `temp_file/PROJECT_SKELETON.md` / `docs/后端战神任务说明书.docx`
