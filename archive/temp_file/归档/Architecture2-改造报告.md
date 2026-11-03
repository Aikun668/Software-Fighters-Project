# AI 服务 Architecture #2 改造报告

> **改造日期**：2026-06-09
> **改造范围**：Python AI 推理服务（`ai-service/`）
> **目标架构**：Frontend → Java (8080, 业务编排) → Python (8001, 纯 AI 推理)

---

## 一、改造动机

**原架构 (Architecture #1)**：Python 通过 HTTP 回调 Java 做数据 CRUD，双向依赖。

**问题**：
- Python 端持有 `java_api_client`，耦合 Java 内部 API
- conversation/profile/dashboard/summary 等 service 实际在做"调 Java 读写 DB"的代理工作
- 数据流向不清晰，调试困难

**新架构 (Architecture #2)**：**Java 单向调用 Python，Python 绝不调 Java**。

核心原则：
1. Java 把所有需要的数据放在请求体中传给 Python
2. Python 只做 AI 计算，返回结果（JSON / SSE）
3. Python 不持久化任何数据（不调 Java API，不写 DB）
4. Java 从 Python 响应中提取结果并自行持久化

---

## 二、端点变更

### 保留并修改（19 个）

| 端点 | 变更类型 | 说明 |
|------|---------|------|
| `POST /internal/profile/chat` | 签名变更 | Java 在请求体传 `student_profile` |
| `POST /internal/resources/generate` | 签名变更 | 同上；done event 返回 content_blocks/questions，不写 DB |
| `POST /internal/tutor/chat` | 签名变更 | Java 传完整 messages + profile，背景画像提取结果只在 done event 返回 |
| `POST /internal/exercise/generate` | 保留 | 原已纯粹，无 Java 调用 |
| `GET→POST /internal/path/{student_id}` | 方法+签名 | 改为 POST，Java 传 profile |
| `GET→POST /internal/profile/workflow/status` | 方法+签名 | 同上 |
| `POST /internal/resources/export-pptx` | 保留 | 无变更 |
| `GET /internal/resources/download-pptx` | 保留 | 无变更 |
| `POST /internal/solve` | 保留 | 无变更 |
| `POST /internal/exercise/error-analysis` | 保留 | 无变更 |
| `POST /internal/exercise/grade` | 保留 | 无变更 |
| `POST /internal/evaluation/report` | 签名变更 | 移除 profile 写回 |
| `GET→POST /internal/knowledge-graph/{course_id}` | 方法+签名 | Java 传 masteries dict |
| `GET→POST /internal/knowledge-graph/{course_id}/node/{node_id}` | 方法+签名 | Java 传 mastery_detail |
| `POST /internal/plans/create-from-path` | 签名变更 | 不再调 Java 创建 plan，返回 steps 给 Java |
| `GET→POST /internal/plans/{plan_id}/status` | 方法+签名 | Java 传 plan + steps |
| `POST /internal/plans/{plan_id}/regression-check` | 签名变更 | 出题/判分/重排纯算法，结果返回 Java |
| `GET→POST /internal/plans/{plan_id}/review-schedule` | 方法+签名 | Java 传 steps 数据 |
| `POST /internal/api/chat` | 签名变更 | 统一对话入口，Java 传完整上下文 |
| `POST /internal/inquiry/resolve` | 签名变更 | 追问解析 + 资源生成 |
| `GET→POST /internal/conversations/{conversation_id}/summary` | 方法+签名 | Java 传 messages 列表 |

### 删除（7 个，Java 自行处理）

| 端点 | 原功能 | Java 替代方案 |
|------|--------|-------------|
| `POST /internal/plans/create` | 创建计划 | Java 直接 INSERT |
| `POST /internal/plans/{id}/progress` | 更新进度 | Java UPDATE + 内置 mastery 公式 |
| `POST /internal/plans/{id}/resume` | 恢复计划 | Java UPDATE status |
| `POST /internal/plans/{id}/node-status-change` | 节点状态联动 | Java UPDATE + 调 /status 重排 |
| `GET /internal/user/dashboard` | 仪表盘 | Java 查自己 DB |
| `POST /internal/conversations/{id}/end` | 结束会话 | Java 自己处理 |

---

## 三、文件变更清单

### 删除的文件（8 个）

| 文件 | 原因 |
|------|------|
| `app/services/java_api_client.py` (415 行) | Python 不再调 Java |
| `app/services/conversation_service.py` (247 行) | 会话 CRUD 由 Java 负责 |
| `app/services/profile_service.py` (124 行) | 画像 CRUD 由 Java 负责 |
| `app/services/dashboard_service.py` (252 行) | 仪表盘查询由 Java 负责 |
| `app/services/summary_service.py` (125 行) | 总结查询由 Java 负责 |
| `app/services/evaluation_report.py` (59 行) | 合并到 evaluation_service |
| `tests/test_conversation_service.py` (364 行) | 对应 service 已删除 |
| `tests/test_profile_service.py` (88 行) | 对应 service 已删除 |

### 修改的文件（11 个）

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `internal_api.py` | -934/+~920 行 | 核心：7 删 6 改 19 修，全部重写 |
| `app/agents/profile_agent.py` | 重写 | 移除 Java 调用，纯内存 extract_and_merge |
| `app/workflows/resource_gen.py` | 重构 | 删除 _persist_node，拆分 _generate_node |
| `app/workflows/learning_path.py` | 重写 | 删除 _persist_node，纯计算返回 |
| `app/api/models.py` | +8 模型 | 新增 PlanStatusRequest、SummaryRequest 等 |
| `app/services/evaluation_service.py` | +generate_report | 合并原 evaluation_report 功能 |
| `app/services/graph_service.py` | 签名变更 | masteries 改由参数传入 |
| `app/services/plan_service.py` | 纯算法 | 移除 Java client 调用 |
| `app/agents/tutor_agent.py` | 修改 | 摘要来源从 Java API 改为 state 注入 |
| `app/workflows/base_workflow.py` | 修改 | 移除 profile_service 依赖 |
| `main.py` | 修改 | 简化 health 端点 + 添加 SecurityMiddleware |
| `temp_file/AI-Java-API-Contract.md` | 重写 | 完整的 Architecture #2 API 文档 |

### 新增的文件（3 个）

| 文件 | 用途 |
|------|------|
| `app/utils/conversation_compress.py` | LLM 对话摘要压缩（Java 可调用 `POST /internal/conversations/{id}/summary`） |
| `app/utils/prompt_guard.py` | LLM prompt 注入防护（8 种常见注入模式过滤） |
| `app/utils/security_middleware.py` | 安全中间件：速率限制 + 服务间认证 + 安全响应头 |

---

## 四、安全加固

| 类别 | 措施 |
|------|------|
| **SSRF 防护** | 原有 IPv4 正则 + 新增十进制/十六进制/八进制 IP 混淆检测 |
| **错误脱敏** | API 响应不再暴露 `str(e)`，统一返回中文用户友好消息 |
| **Prompt 注入** | 过滤 "ignore previous instructions"、`<|im_start|>`、`[INST]` 等注入模式 |
| **速率限制** | 每 IP 60s 窗口最多 120 请求 |
| **服务间认证** | `Authorization: Bearer <AI_SERVICE_SHARED_SECRET>` 共享密钥 |
| **安全头** | X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Cache-Control, Permissions-Policy |
| **PII 脱敏** | 日志中移除用户回答内容，只记录数量 |
| **SSE 防注入** | 过滤用户输入中的 `\n\n` 和 `\ndata:` 控制序列 |

---

## 五、SSE done event 标准化

所有流式端点统一在 `done` 事件中包含完整结果：

```json
{
  "type": "done",
  "content_blocks": [...],
  "questions": [...],
  "steps": [...],
  "response": "完整 AI 回复文本",
  "profile_delta": {...},
  "conversation_id": 42,
  "error": null
}
```

流式输出从逐字符改为 4 字符批量发送，大幅减少 SSE 事件数量。

---

## 六、数据流向示意

```
┌──────────┐   请求体: {messages, profile, plan, steps...}   ┌──────────────┐
│          │ ──────────────────────────────────────────────> │              │
│   Java   │                                                │   Python AI  │
│  (8080)  │ <────────────────────────────────────────────── │   (8001)     │
│          │   响应: {success, data} / SSE {type: "done"}    │              │
└────┬─────┘                                                └──────────────┘
     │
     │ 自行持久化: plan CRUD, profile update, resource save...
     v
  ┌──────┐
  │  DB  │
  └──────┘
```

---

## 七、验证结果

- 全量语法检查：**PASS**（`python -m compileall` 零错误）
- 受影响测试：`test_api.py` + `test_evaluation.py` **56/56 通过**
- 残留 Java 引用检查：`app/` 目录下 `java_api_client|conversation_service|profile_service` **零匹配**

---

## 八、Java 端对接要点

详见 `temp_file/AI-Java-API-Contract.md`，核心变更 Java 团队需关注：

1. 7 个端点已删除，Java 需自行实现对应 CRUD
2. 6 个端点从 GET 改为 POST，调用方式需调整
3. 所有端点请求体需附带完整上下文（profile、messages、steps 等）
4. 从 SSE `done` event 中提取 `profile_delta`、`content_blocks`、`questions` 并持久化
5. 建议配置环境变量 `AI_SERVICE_SHARED_SECRET` 开启服务间认证
