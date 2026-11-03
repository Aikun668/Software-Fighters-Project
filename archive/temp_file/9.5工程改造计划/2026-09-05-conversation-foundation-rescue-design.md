# 对话底座救援设计

## 目标

本轮不增加任何新 Agent 或多模态能力，只把文本聊天做成可靠的默认入口：

1. 页面只走真实后端聊天链路。
2. 普通学习问答默认交给 TutorAgent。
3. 只有明确要求生成计划、资源、练习或图解时，才进入复杂能力编排。
4. 历史、画像、知识库按相关性注入，不再全塞。
5. 每次改动可由评测集回归验证。

## 已确认的系统判断

系统已有统一聊天入口、SSE、会话 ID、学生画像、ChatCenter、RouterAgent、ResultAgent、TutorAgent 和多种能力模块。问题不是能力不足，而是主路径过重：

- AITutor.vue 仍有本地模拟回答，而 frontend/src/api/chat.ts 已有真实 SSE 客户端。
- auto 模式主要用关键词和意图评分，容易把普通对话误判成能力调用。
- TutorAgent 可能直接拼接最近历史、学生画像与知识库，造成上下文噪声。
- 缺少一套可量化的稳定性评测。

## 目标架构

浏览器
→ frontend/src/api/chat.ts
→ POST /internal/api/chat
→ 输入清洗与请求校验
→ ContextBuilder
→ CapabilityGate
  - NORMAL_CHAT → TutorAgent
  - PLAN / RESOURCE / EXERCISE / VISUALIZATION → RouterAgent → ExecutionPlan → ResultAgent
→ ResponseSanityCheck
→ SSE: content / inquiry / recommendation / error / done

## 架构规则

### CapabilityGate

CapabilityGate 只回答一个问题：这条话是否明确需要专用产物或专用工作流？

一级结果固定为：

- NORMAL_CHAT
- PLAN
- RESOURCE
- EXERCISE
- VISUALIZATION

默认值永远是 NORMAL_CHAT。单个关键词不构成调用依据，必须存在明确动词和明确产物。

| 输入 | 路由 |
|---|---|
| 知识图谱是什么？ | NORMAL_CHAT |
| 我感觉 TCP 没学懂，简单讲讲 | NORMAL_CHAT |
| 给我画一张 TCP 三次握手流程图 | VISUALIZATION |
| 帮我出 5 道进程调度选择题 | EXERCISE |
| 基于本周课程制定 7 天计划 | PLAN |

solve_problem、code_example 和普通解释属于 TutorAgent 的回答策略；不再作为一级分流。diagnose 仅在用户明确要求评估掌握情况时才允许成为二级策略。

### ContextBuilder

按固定顺序构建模型上下文：

1. 稳定系统指令；
2. 早期对话摘要；
3. 最近完整对话轮次；
4. 相关学生画像片段；
5. 相关知识库证据；
6. 当前用户消息。

当前消息必须最后出现。摘要是状态记录，不得伪造事实。画像和知识库在不相关时应为空。

### ResponseSanityCheck

第一轮只检查高置信异常：

- 空回答
- 过度重复
- 明显截断
- 内部提示词或 JSON 泄露
- 请求语言明显不一致
- SSE 流未终止

最多重试一次；再次失败返回可恢复错误。不能用“另一个 LLM 说正确”替代真实准确性评估。

## 阶段与完成证据

| 阶段 | 目标 | 完成证据 |
|---|---|---|
| P0 | 唯一真实聊天链路 | 页面网络记录、后端日志、SSE 合同测试 |
| P1 | 默认聊天与能力调用分流 | CapabilityGate 单测、路由审计 |
| P2 | 上下文相关且可控 | ContextBuilder 单测、多轮样例 |
| P3 | 输出稳定与安全降级 | 健全性检查单测、故障注入 |
| P4 | 可量化评测与回归 | 60 条评测集、报告、门禁 |
| P5 | 恢复能力扩展 | P4 门槛全部达标后，单模块解冻 |

## 首轮门槛

- 能力误触发率 ≤ 5%。
- 明确能力请求识别率 ≥ 90%。
- 20 条上下文抽检至少 18 条正确承接。
- 空回答、明显重复、截断、内部提示泄露均为 0。
- 普通问答成功 SSE done 率 ≥ 99%。
- 核心指标退化时不允许进入 P5。

## 明确不做

- 不新建第 12 个 Agent。
- 不重写资源、图解、练习等能力内部实现。
- 不做模型更换或大规模 RAG 改造。
- 不全量注入学生画像、历史或知识库。
- P0–P4 期间不接受能力扩展插队。

## 观测字段

每次请求透传 trace_id，并仅记录脱敏字段：

trace_id、conversation_id、route、route_reason、context_turn_count、profile_fields_used、kb_chunks_used、model_latency_ms、retry_count、sse_terminal_event、error_code。

不记录完整画像、密钥和完整私密对话。
