# Day 4 进度总结 | 2026-05-27 ~ 2026-05-28

---

## 一、Day 4 做了什么

Day 4 目标：关闭 Mock，全系统接入真实能力。分两轮执行。

---

### Round 1：真实 LLM 全线打通 ✅（5/5 Agent 完成）

**背景**：Day 3 搭好 5 个 Agent 骨架，全部 Mock 模式可跑。Round 1 全部切到真实 Spark API。

**1. 基础设施修复（3 项）**

| 修复项 | 问题 | 影响 |
|--------|------|------|
| JSON 解析正则 Bug | 原正则 `\{[\s\S]*?\}` 遇嵌套 JSON 在第一个 `}` 截断，画像永远不更新 | ProfileAgent 核心功能失效 |
| WebSocket 超时缺失 | `chat_stream()` 无超时无异常覆盖，API 卡住永久挂起 | 所有流式端点可用性风险 |
| `.env` 缺少开关 | `USE_MOCK_LLM` 默认 true，Agent 传 false 也被覆盖 | 切真实 LLM 不生效 |

**修复**：新建 `json_parser.py`（3 层容错）、`llm_service.py` 加 asyncio.timeout + open_timeout=30 + OSError 覆盖、`.env` 加 `USE_MOCK_LLM=false`。

**2. 5 个 Agent 真实 LLM 接入**

| Agent | 改动 | 核心能力 |
|-------|------|------|
| ProfileAgent | extract/response 节点切真实 LLM，JSON 解析改用 3 层容错 | 对话式画像提取 |
| TutorAgent | 流式 LLM 响应 + 画像/知识上下文注入 prompt | 智能答疑 |
| ContentAgent | 重写生成节点：按 role 路由到 code/deep_dive/outline 子 prompt，逐块 LLM 生成 | 教学内容生成 |
| ExerciseAgent | plan 节点 LLM 规划题型蓝图，generate 节点逐题 LLM 生成 + quiz_validator 校验 | 个性化出题 |
| PathAgent | draft 节点 LLM 设计学习路径，revise 节点 LLM 自审查 | 学习路径规划 |

**3. 测试体系**：75 用例全部通过（~1.6 秒），覆盖 JSON 解析/Prompt 加载/LLM 服务/5 Agent/API 端点。

---

### Round 2：ChromaDB RAG 知识库检索 ✅（主体完成，2 项待修）

**背景**：TutorAgent 此前检索节点是硬编码 mock 文本，不是真正从知识库查的。

**1. ChromaDB 知识库接入**

- 绑定 ONNX 本地 embedding 模型（`all-MiniLM-L6-v2`）——本地推理，零 API 依赖
- 向量检索失败时自动降级为字符级关键词匹配，不阻塞服务
- 新增 `add_documents()` 批量导入接口 + `is_empty()` 状态检查

**2. 文档导入工具**

- `scripts/import_knowledge.py`：扫描 `knowledge_docs/` 下 `.md/.txt` → 自动分块 → 入库
- 分块参数 chunk_size=512, overlap=50（适配中文分隔符）
- upsert 去重，重复导入不产生脏数据

**3. TutorAgent 切真实检索**

- `_retrieve_node` 去掉硬编码 mock，接入 `get_kb().format_context(query, top_k=3)`
- 空库/检索异常 → knowledge_context 降级为空字符串，对话不中断
- system prompt 加入知识上下文占位符

**4. 测试**：新增 11 用例，全量 86/86 通过。

**5. 待修项（明天改）**

| # | 问题 | 影响 |
|---|------|------|
| 1 | 分块器 overlap 生效范围有限，需换回标准库实现 | 部分 chunk 边界上下文丢失 |
| 2 | 清除测试用的生成内容（知识文档等我放） | 避免脏数据 |

---

## 二、系统当前能力总览

| 端点 | 方法 | 功能 | 状态 |
|------|------|------|:--:|
| `/internal/profile/chat` | POST | 对话式画像构建（SSE 流式） | ✅ |
| `/internal/tutor/chat` | POST | RAG 智能答疑（SSE 流式） | ✅ |
| `/internal/resources/generate` | POST | 教学内容生成（SSE 流式） | ✅ |
| `/internal/exercise/generate` | POST | 个性化出题（SSE 流式） | ✅ |
| `/internal/path/{student_id}` | GET | 学习路径规划 | ✅ |

**5 个 Agent 全部接入真实 Spark API，TutorAgent 接入 ChromaDB RAG 知识库检索。**

---

## 三、技术要点

- **LLM**：讯飞星火 v4.0 Ultra，WebSocket HMAC-SHA256 签名，流式+非流式双模式
- **Agent 框架**：LangGraph StateGraph，每个 Agent 独立编译状态图
- **知识库**：ChromaDB + ONNX 本地 embedding，向量检索 + 关键词降级双轨
- **容错**：全链路 fallback——LLM 失败/Mock 降级 → JSON 解析失败/json_repair 修复 → 向量检索失败/关键词降级 → DB 不可用/内存降级
- **测试**：86 用例，~6 秒全量通过，Mock 隔离无外部依赖

---

## 四、各角色后续

| 角色 | 待办 |
|------|------|
| 算法（我） | Day 5 Round 3（MySQL 画像持久化）、知识文档准备、真实 API 端到端联调 |
| 后端 | 5 个 `/internal` 端点联调、`student_profiles` 表迁移、用户认证对接 |
| 前端 | SSE 流式输出对接（token/progress/content_block/done 事件）、画像面板、学习路径可视化 |

---

## 五、关键文件索引

```
ai-service/
├── app/
│   ├── agents/
│   │   ├── base_agent.py          # Agent 基类
│   │   ├── profile_agent.py       # 画像构建 Agent
│   │   ├── tutor_agent.py         # RAG 答疑 Agent ★ Round 2
│   │   ├── content_agent.py       # 内容生成 Agent
│   │   ├── exercise_agent.py      # 出题 Agent
│   │   └── path_agent.py          # 学习路径 Agent
│   ├── services/
│   │   ├── llm_service.py         # Spark LLM 封装
│   │   └── knowledge_base.py      # ChromaDB 知识库 ★ Round 2
│   ├── utils/
│   │   ├── json_parser.py         # JSON 3 层容错解析
│   │   ├── prompt_loader.py       # Prompt 加载器
│   │   ├── quiz_validator.py      # 题目校验
│   │   └── text_splitter.py       # 文本分块 ★ Round 2
│   ├── models/profile.py          # 学生画像 ORM
│   └── db/database.py             # MySQL 异步引擎
├── scripts/
│   └── import_knowledge.py        # 文档导入脚本 ★ Round 2
├── prompts/                       # Prompt YAML 文件（10+）
├── tests/                         # 86 用例
├── internal_api.py                # 内部 API 路由
├── main.py                        # FastAPI 入口
└── .env                           # 环境配置
```

---

明天继续 Round 3（MySQL 画像持久化）+ 知识文档准备。
