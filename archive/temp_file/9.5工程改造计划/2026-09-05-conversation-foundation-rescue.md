# 对话底座救援实施计划

> 执行时按任务顺序逐个完成。当前工作区没有项目源码，且不是 Git 仓库；因此不能猜测后端文件路径。Task 1 完成前，不得开始改业务代码。

**目标：** 将个人学习系统的默认文本聊天收敛为“普通对话直达 TutorAgent，明确能力才进入复杂编排”的可靠底座。

**对应设计：** docs/superpowers/specs/2026-09-05-conversation-foundation-rescue-design.md

**全局约束：**

- 已知锚点：frontend/src/views/AITutor.vue、frontend/src/api/chat.ts、POST /internal/api/chat。
- 除锚点外，所有真实文件路径均以 Task 1 搜索结果为准。
- P0–P4 只修聊天主链路；资源、图解、练习、闪卡、知识图谱和多 Agent 扩展一律冻结。
- 路由不确定时必须 NORMAL_CHAT。
- 每一阶段都先有测试，再改实现；每阶段通过验收后才进入下一阶段。

---

## Task 1：源码入场与基线盘点

**产物：**

- docs/conversation-rescue/repo-map.md
- docs/conversation-rescue/baseline.md

**步骤：**

- [ ] 在真实项目根目录运行：

    rg -n -S "simulateStreamResponse|preset|/internal/api/chat|UnifiedChatRequest|ChatCenter|RouterAgent|ResultAgent|TutorAgent|IntentRegistry|IntentExtractor" . -g '!node_modules' -g '!dist' -g '!build'

- [ ] 在 repo-map.md 按下表填入搜索证据。没有证据一律写“未发现”，不猜路径。

| 责任 | 实际文件 | 符号或路由 | 上游 | 下游 |
|---|---|---|---|---|
| 聊天页面 |  |  |  |  |
| SSE 客户端 |  |  |  |  |
| HTTP 入口 |  |  |  |  |
| ChatCenter |  |  |  |  |
| Router / Intent |  |  |  |  |
| TutorAgent |  |  |  |  |
| SSE 发送器 |  |  |  |  |
| 测试配置 |  |  |  |  |

- [ ] 运行以下命令，找到实际测试框架与启动命令：

    find . -maxdepth 3 \( -name package.json -o -name pyproject.toml -o -name pytest.ini -o -name tox.ini -o -name vitest.config.* -o -name jest.config.* \) -print

- [ ] 在 baseline.md 记录前端、后端、端到端测试命令及结果。
- [ ] 在浏览器分别发送一条普通问答和一条明确能力请求，记录 Network 请求、首个 SSE 事件、终止事件、页面回答与后端日志关联信息。
- [ ] 验收：能画出从 AITutor.vue 到 done 事件的真实调用路径。若缺任意一环，停止并先解决源码版本或部署不一致。

## Task 2：P0 删除页面模拟回答，打通唯一真实入口

**修改对象：** frontend/src/views/AITutor.vue、frontend/src/api/chat.ts，以及 Task 1 找到的前端测试目录。

**失败测试先行：**

- [ ] 写一个页面测试：输入“什么是进程？”后，断言真实 SSE 客户端被调用一次，页面显示其 content 事件；页面不出现模拟或默认回答。
- [ ] 运行该测试，确认在旧 Mock 路径仍存在时失败。

**最小实现：**

- [ ] 删除或禁用 simulateStreamResponse、固定预设答案、未匹配问题的默认本地回答和相关定时器。
- [ ] sendMessage 只做四件事：创建用户气泡、调用真实客户端、按 SSE 事件更新助手气泡、在 error 时恢复输入并显示真实错误。
- [ ] 保持 API 客户端作为唯一 SSE 解析位置；处理取消、非 2xx、解析异常与终止事件，绝不回退到假内容。
- [ ] 运行前端测试和手工验证。
- [ ] 验收：DevTools 每次发送都产生 POST /internal/api/chat；后端关闭时页面显示错误而不是本地回答。

## Task 3：P0 固化 SSE 终止合同

**修改对象：** Task 1 定位的 HTTP 路由文件、SSE 发送器和后端测试目录。

**失败测试先行：**

- [ ] 成功请求：事件至少有一个 content，最后一个事件是 done。
- [ ] Agent 异常：流以 error 或项目既有的明确终止语义结束，不得无限悬挂。
- [ ] 非法请求：返回可识别错误，不进入 Agent 调度。
- [ ] 运行测试，确认旧缺口会失败。

**最小实现：**

- [ ] 在流生成边界设置单一终止责任；Agent 内部不随意发送 done。
- [ ] 成功、校验拒绝、内部异常三类分支都有明确最终事件。
- [ ] 运行全部聊天后端测试。
- [ ] 验收：所有 SSE 测试通过，页面不再有“加载中永远不结束”。

## Task 4：P1 建立保守 CapabilityGate

**新增对象：** 在 Task 1 定位的聊天域目录中创建 capability_gate（或在现有路由模块中添加同等职责）；新增对应单测。

**接口：**

CapabilityDecision = kind、reason、confidence

kind 只能是 NORMAL_CHAT、PLAN、RESOURCE、EXERCISE、VISUALIZATION。

**失败测试先行：**

- [ ] “知识图谱是什么？” → NORMAL_CHAT
- [ ] “我感觉 TCP 没学懂，简单讲讲” → NORMAL_CHAT
- [ ] “给我画一张 TCP 三次握手流程图” → VISUALIZATION
- [ ] “帮我出 5 道进程调度选择题” → EXERCISE
- [ ] “基于本周课程制定 7 天计划” → PLAN
- [ ] 运行测试，确认新类型和函数不存在时失败。

**最小实现：**

- [ ] 非 auto 的显式 mode 优先。
- [ ] auto 只接受“明确动词 + 明确产物”的高置信证据。
- [ ] 单个名词、模糊诉求、概念解释和例子请求必须回退 NORMAL_CHAT。
- [ ] 旧 IntentRegistry / IntentExtractor 只保留为诊断或二级提示，不能直接决定一级路径。
- [ ] ChatCenter：NORMAL_CHAT 直达 TutorAgent；其余四类才进入 RouterAgent → ExecutionPlan → ResultAgent。
- [ ] 验收：普通问答不创建复杂 ExecutionPlan，5 条合同样例全部通过。

## Task 5：P1 路由观测与误触发审计

**产物：**

- 脱敏路由日志
- docs/conversation-rescue/routing-audit.md

**步骤：**

- [ ] 写失败测试：日志包含 route=NORMAL_CHAT；不包含 student_profile 全量内容或 full_history。
- [ ] 透传 trace_id；记录 route、route_reason、context_turn_count、model_latency_ms、retry_count、sse_terminal_event。
- [ ] 使用 20 条样例审计：普通问答 12、上下文追问 4、明确能力 4。
- [ ] 在 routing-audit.md 记录每条实际 route 与是否正确。
- [ ] 验收：无证据的能力调用全部回落为 NORMAL_CHAT；日志不泄露隐私。

## Task 6：P2 引入 ContextBuilder

**新增对象：** 在 TutorAgent 所在聊天域新建 context_builder（若已有上下文模块则扩展其中），并新增单测。

**接口：**

BuiltContext = system、summary、recent_turns、profile_facts、kb_evidence、current_message。

**失败测试先行：**

- [ ] 当前问题“TCP 为什么需要三次握手？”能保留最近“我们在学 TCP/IP”。
- [ ] 画像中的“偏好先直观后公式”可以保留；与问题无关的字段不得注入。
- [ ] KB 中 TCP 建连片段可以保留；二叉树遍历片段不得注入。
- [ ] 当前消息永远在最终用户位置。

**最小实现：**

- [ ] 按 system → summary → recent turns → related profile → related KB → current message 的顺序构建。
- [ ] 最近窗口保持完整轮次，不能切断一问一答。
- [ ] 摘要缺失时保持空，不临时杜撰。
- [ ] TutorAgent 只接收 BuiltContext，不再自行 messages[-N:] 和全量 profile dump。
- [ ] 验收：进程后追问“那线程呢？”可承接；“不是，我说的是虚拟内存。”能覆盖旧主题。

## Task 7：P2 维护对话摘要

**修改对象：** 会话持久化或 ChatCenter、ContextBuilder、上下文测试。

**步骤：**

- [ ] 写失败测试：旧摘要写“用户在学习进程调度”时，当前“不是，我现在问虚拟内存”必须优先。
- [ ] 对话超过最近窗口或一个主题完成时才更新摘要。
- [ ] 摘要仅保存确认主题、已解决点、当前卡点、明确偏好；不得写未经证实的能力评价。
- [ ] 运行所有 context 与 tutor 测试。
- [ ] 验收：长对话仍能记住主题，但不压制当前输入。

## Task 8：P3 加入 ResponseSanityCheck 与一次重试

**新增对象：** response_sanity（或扩展现有 validator）与对应测试。

**失败测试先行：**

- [ ] 空字符串 → RETRY_ONCE。
- [ ] 大量重复片段 → RETRY_ONCE。
- [ ] 含内部提示字段的 JSON → USER_SAFE_ERROR。
- [ ] 正常中文学习回答 → ACCEPT。
- [ ] 连续两次失败时 SSE 最终为 error，而不是伪造 content。

**最小实现：**

- [ ] 机械优先检测：空、重复、截断、内部提示泄露、语言明显冲突。
- [ ] 第一次失败以相同 BuiltContext 重试一次。
- [ ] 第二次失败返回可恢复错误与脱敏 error_code。
- [ ] 检查器不得改写正常回答，也不承担“事实绝对正确”的判定。
- [ ] 验收：失败注入、成功重试和正常回答三类测试均通过。

## Task 9：P4 建立版本化评测集

**新增文件：**

- evals/chat_foundation_v1.jsonl
- evals/README.md
- docs/conversation-rescue/eval-rubric.md

**步骤：**

- [ ] 建立 60 条 JSONL 样例，字段为 id、category、turns、current_message、expected_route、must_include、must_not_include、evaluator_notes。
- [ ] 类别固定为：普通问答 20；上下文承接 12；用户纠正 8；歧义追问 8；明确能力请求 8；不得误触发能力 4。
- [ ] 评分维度为：路由正确、回答当前问题、上下文一致、无依据编造、中文学习助手风格；每项取 pass / fail / needs-review。
- [ ] 人工复查 60 条 expected_route，防止把“知识图谱是什么”误写成图谱生成。
- [ ] 验收：数据可版本控制，且每条都能独立执行。

## Task 10：P4 评测运行器与回归门禁

**新增对象：** 在后端现有 CLI 或脚本目录创建 run_chat_eval；新增测试与 evals/reports 目录。

**失败测试先行：**

- [ ] 用假的聊天客户端运行 60 条评测。
- [ ] 断言报告含 total=60、capability_false_trigger_rate、sse_done_rate 和人工复核列表。
- [ ] 先让测试因运行器不存在而失败。

**最小实现：**

- [ ] 运行器绕开页面，调用同一个聊天入口或 ChatCenter。
- [ ] 每条报告记录 route、终止事件、输出摘要、机器断言结果和人工复核标记；不得写完整私密历史。
- [ ] 生成以 UTC ISO-8601 时间戳命名的报告文件，例如 evals/reports/chat_foundation_2026-09-05T12-00-00Z.json。
- [ ] 在 CI 或最少本地发布脚本中执行核心合同；路由和 SSE 退化必须非零退出。
- [ ] 验收门槛：误触发率 ≤5%，明确能力请求识别率 ≥90%，SSE done 率 ≥99%，空/重复/截断/内部泄露为 0。

## Task 11：P5 解冻评审

**产物：** docs/conversation-rescue/p4-release-review.md

**步骤：**

- [ ] 重跑 60 条评测。
- [ ] 随机抽检 20 条真实回答，按 eval-rubric.md 评分。
- [ ] 所有 P4 门槛达标时写 GO；否则写 HOLD，并精确列出回到 Task 2–10 中哪一项。
- [ ] 只有 GO 时，资源、练习、图解、计划四类中选择一个作为下一张独立计划；不能一次全开。
- [ ] 验收：能力扩展由指标触发，不再由“看起来差不多”触发。

## 停止规则

以下任一出现，立即停止向后推进并回到最近任务：

- 页面仍返回本地模拟答案；
- 普通问答进入复杂 ExecutionPlan；
- SSE 没有终止事件；
- 当前用户纠正被旧历史压过；
- 评测核心指标退化。

这轮计划最重要的节奏是：先让“随便问一句都能好好回”稳定下来，再让聪明的能力一个个挂回来。
