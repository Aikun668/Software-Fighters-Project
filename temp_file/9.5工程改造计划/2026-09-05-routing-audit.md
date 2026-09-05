# Task 5 · 路由观测与误触发审计（routing-audit）

> 生成时间：2026-09-05。分支 `后端改造分支`。基于 Task 4 CapabilityGate 落地后的 ChatCenter 路由。
> 说明：计划原文的产物路径是 `docs/conversation-rescue/routing-audit.md`；实际沿用本团队惯例，与 baseline / repo-map 同目录存放。

## 一、观测日志落地情况

**实现位置**：`ai-service/app/services/routing_audit.py`（白名单 + 脱敏构造 + 单行 JSON 输出）＋ `ChatCenter.route/execute`（元数据注入与边界采集，`chat_center.py`）。

每次聊天请求在 ChatCenter 边界产出一条日志（logger 名 `routing.audit`），字段与设计文档"观测字段"对齐：

| 字段 | 现状 |
|---|---|
| trace_id | ✅ 透传：调用方在 context 中给 `trace_id` 即原样记录；缺失时自动生成 12 位短 ID |
| conversation_id | ✅ 来自请求 context（Java 传入） |
| route / route_reason | ✅ CapabilityDecision（Task 4），如 `capability_evidence:verb_count_exercise` |
| context_turn_count | ✅ 历史消息条数（自动剔除末尾的当前消息；只记数字，不记正文） |
| model_latency_ms | ✅ ResultAgent 管线耗时（perf_counter） |
| retry_count | 恒 0，Task 8 ResponseSanityCheck 接入后有意义 |
| sse_terminal_event | ✅ 管线视角的终止事件（done/error/inquiry；管线抛异常记 error）。注意：这是 ChatCenter 边界观测，线级（wire-level）终止由 Task 3 的 SSE 合同测试保障，两者当前一致 |
| profile_fields_used / kb_chunks_used | 预留，Task 6 ContextBuilder 起填充 |
| error_code | 预留，Task 3/8 错误码体系接入后填充 |

**脱敏验证**：`tests/test_routing_audit.py` 用哨兵值断言——画像值、历史正文、回答正文均不出现在日志中；记录键必须是白名单子集（`ALLOWED_KEYS`）。不记录完整画像、完整历史。

**待办（一行接线）**：`internal_api.py` 正由 Task 3 进程改造中，本任务未触碰；待其合入后在 `_unified_chat` 的 context 中补传 `body.trace_id`（`UnifiedChatRequest` 增加可选字段即可），前端/Java 发 trace_id 链路即通。

## 二、20 条样例路由审计（普通问答 12 / 上下文追问 4 / 明确能力 4）

执行方式：离线直连 `ChatCenter.route`（mock IntentExtractor，无 LLM 调用，确定性可复跑）；同一组样例已固化为回归测试 `tests/test_routing_audit.py::TestTwentySampleRoutingAudit`。

| # | 样例 | 期望 | 实际 route | 结果 | 任务数 | route_reason |
|---|---|---|---|---|---|---|
| 1 | 什么是进程？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 2 | 为什么TCP需要三次握手？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 3 | 讲讲虚拟内存的作用 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 4 | 操作系统和数据库有什么区别？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 5 | 我感觉TCP一直没搞懂 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 6 | 这个再讲简单一点 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 7 | 你刚才那个例子我没听明白 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 8 | 举个例子说明一下进程和线程 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 9 | 二叉树的中序遍历是什么？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 10 | 帮我理解一下递归 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 11 | 什么是知识图谱？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 12 | Python 的 GIL 是什么？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 13 | 那线程呢？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 14 | 为什么？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 15 | 不对，我说的是虚拟内存 | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 16 | 那这个机制在Windows上也一样吗？ | NORMAL_CHAT | NORMAL_CHAT | ✅ | 1 | no_capability_evidence |
| 17 | 帮我出 5 道进程调度选择题 | EXERCISE | EXERCISE | ✅ | 1 | capability_evidence:verb_count_exercise |
| 18 | 给我画一张 TCP 三次握手流程图 | VISUALIZATION | VISUALIZATION | ✅ | 1 | capability_evidence:draw_diagram |
| 19 | 基于本周课程制定 7 天计划 | PLAN | PLAN | ✅ | 1 | capability_evidence:make_plan |
| 20 | 帮我找几个操作系统的学习资源 | RESOURCE | RESOURCE | ✅ | 1 | capability_evidence:request_material |

**结果：20/20 正确；无证据输入 100% 回落 NORMAL_CHAT（误触发 0/16）；4 条明确能力请求全部识别且均只产生单任务计划。**

## 三、验收对照

| 计划要求 | 结果 |
|---|---|
| 失败测试：日志包含 route=NORMAL_CHAT；不含 student_profile 全量/ full_history | ✅ `TestRoutingAuditLog::test_normal_chat_logs_route_and_no_privacy`（哨兵值断言） |
| 透传 trace_id | ✅ context 透传 + 缺失自动生成（请求体字段的最终接线待 Task 3 的 internal_api 合入，见上） |
| 记录 route / route_reason / context_turn_count / model_latency_ms / retry_count / sse_terminal_event | ✅ 全部落地（retry_count 恒 0 待 Task 8） |
| 20 条样例审计并记录实际 route 与是否正确 | ✅ 上表，20/20 |
| 验收：无证据能力调用全部回落 NORMAL_CHAT | ✅ 16/16 |
| 验收：日志不泄露隐私 | ✅ 白名单 + 哨兵断言 |

## 四、给后续 Task 的输入

1. **Tutor 图解增强是普通链路上的隐藏能力触发**（Task 4 已记录）：`AutoCenter._run_tutor` 在每次答疑后跑 `_maybe_visualize`，预过滤弱信号时默认放行 → 每条普通问答都可能多一次可视化管线 LLM 调用（延迟+误触发面）。属于回答路径而非路由，本任务未改；建议在 Task 6（ContextBuilder/TutorAgent 输入改造）或 P5 解冻评审时处置：普通链路默认关闭，仅 VISUALIZATION 路由开启。
2. **exercise 中心 3m40s 延迟**（baseline 遗留）会在真实请求的 `model_latency_ms` 中暴露，建议 Task 9 评测运行器对 latency 设阈值告警。
3. Task 10 回归门禁可直接消费 `routing.audit` 日志与 `TestTwentySampleRoutingAudit` 样例集（60 条评测集（Task 9）建议从这 20 条扩容）。
