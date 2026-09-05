# evals — 对话底座评测集（Task 9 · P4）

> 版本：`chat_foundation_v1`（2026-09-05 冻结）。
> 隶属改造计划：`temp_file/9.5工程改造计划/2026-09-05-conversation-foundation-rescue.md` Task 9。
> 评分标准：`temp_file/9.5工程改造计划/2026-09-05-eval-rubric.md`。

## 文件

| 文件 | 说明 |
|---|---|
| `chat_foundation_v1.jsonl` | 60 条评测样例，每行一条独立可执行的 JSON |
| `verify_routes.py` | 数据一致性复查：把每条样例跑过真实 CapabilityGate（纯规则、无 LLM），报告 expected_route 分歧 |

## 数据模式

每行字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `类别前缀-序号`，如 `nq-01`、`cap-03` |
| `category` | string | 六类之一（见下表） |
| `turns` | array | 先前对话轮次 `[{role, content}]`，独立话题为 `[]` |
| `current_message` | string | 本轮用户输入（评测时最后一条消息） |
| `expected_route` | string | 人工标定的一级路由：`NORMAL_CHAT / PLAN / RESOURCE / EXERCISE / VISUALIZATION` |
| `must_include` | array[str] | 机器断言：回答必须包含的子串（话题锚点/关键词） |
| `must_not_include` | array[str] | 机器断言：回答不得包含的子串（内部泄露标记等） |
| `evaluator_notes` | string | 人工评分要点（供 Task 11 复查用） |

## 类别构成（固定 60 条）

| category | 数量 | expected_route | 考什么 |
|---|---|---|---|
| `normal_qa`（nq-） | 20 | NORMAL_CHAT | 独立学习问答的基本质量 |
| `context_followup`（cf-） | 12 | NORMAL_CHAT | 多轮承接："那线程呢？""第二步我没看懂" |
| `user_correction`（uc-） | 8 | NORMAL_CHAT | 当前纠正必须覆盖旧话题（"不是，我说的是挥手"） |
| `ambiguous_followup`（af-） | 8 | NORMAL_CHAT | 指代消解与合理默认（"它有什么优缺点？"） |
| `capability_request`（cap-） | 8 | 四类能力 | 明确动词+明确产物才放行（含 3 条设计文档合同样例） |
| `no_false_trigger`（nt-） | 4 | NORMAL_CHAT | 名词陷阱："知识图谱是什么？""举个例子"不得误触发 |

## 使用规则

- **v1 冻结**：本文件不改写、不追加；样例有问题走新版本文件（`chat_foundation_v2.jsonl`），保证回归可比。
- 运行器（Task 10 `run_chat_eval`）绕开页面、逐条调用与线上相同的聊天入口；`must_include / must_not_include` 做机器断言，其余维度按 rubric 人工评。
- 复查命令（数据侧守门， CapabilityGate 与标定出现分歧时退出码 1）：

  ```bash
  cd ai-service && python ../evals/verify_routes.py
  ```

- Task 10 的报告写入 `evals/reports/`（UTC 时间戳命名）。

## 复查记录（人工复查 expected_route，2026-09-05）

- 机械复查：60/60 与真实 `CapabilityGate.decide()` 零分歧（含"知识图谱是什么？"正确落 NORMAL_CHAT）。
- 人工抽检：cap-01/03/05 采用设计文档合同样例原文；nt-01 为计划点名的防误触发样例；uc-01 采用计划原例"不是，我说的是挥手"。
- 标定原则：能力请求必须"明确动词 + 明确产物"成对；模糊诉求、概念解释、举例请求一律 NORMAL_CHAT。

## 评测运行器（Task 10 · 2026-09-05 接入）

`run_chat_eval.py`：绕开页面，逐条调用与线上相同的 `ChatCenter.route`；
一级路由指标真实（确定性 CapabilityGate，离线可复跑），回答由可注入客户端产出。

```bash
# 标准离线运行（fake 客户端 + 真实路由），报告写入 evals/reports/
python evals/run_chat_eval.py

# 故障注入：验证 SSE 退化会被门禁拦下（退出码 1）
python evals/run_chat_eval.py --client broken
```

- 门禁：误触发率 ≤5%、能力识别率 ≥90%、SSE done 率 ≥99%、空/重复/截断/泄露 = 0；任一不达标退出码 1。
- 客户端协议：`async run(sample) -> (answer, terminal_event)`；真实 LLM 客户端在 Task 11 解冻评审时按同协议接入。
- 离线运行的 `needs_review` 条目 = `must_include` 无法离线验证的内容断言；真实运行后由人工按 rubric 裁决。
- 回归测试：`ai-service/tests/test_run_chat_eval.py`（含路由退化/SSE 退化非零退出的门禁测试）。
