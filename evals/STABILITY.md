# chat_stability_v1 — 普通聊天稳定性回归集

> 版本：`chat_stability_v1`（2026-09-06 建立）。
> 定位：**小而稳、改动后必跑**的离线回归（19 条、秒级、零 LLM 调用），
> 与 `chat_foundation_v1`（60 条冻结评测集，Task 10/11 门禁指标口径）互补，不替代。

## 解决的问题

9.5 工程改造计划（`archive/temp_file/9.5工程改造计划/2026-09-05-conversation-foundation-rescue.md`）
收敛出的普通聊天合同，需要一套**每次改动后都能机器判定**的回归，重点盯五类风险：

| 风险 | 回归手段 |
|---|---|
| 普通提问误触发复杂能力 | 真实 `CapabilityGate.decide` + `ChatCenter.route` 全量断言路由与首任务模式 |
| 二轮追问丢上下文 | 上一轮问答必须随任务上下文下发（锚点断言）+ `context_turn_count` 审计 |
| 空回答 / 内部泄露 | 走生产 `run_with_sanity_check` 重试编排，脚本化 generate 注入故障 |
| 异常提示泄漏 / 悬挂 | 错误终态可观测（error 事件 + done 收尾）+ 异常细节不外泄（真实执行路径） |
| 无关画像干扰 | `ContextBuilder` 只注入与当前话题相关的画像片段（词面交集合同） |

## 文件

| 文件 | 说明 |
|---|---|
| `chat_stability_v1.jsonl` | 19 条回归样例，每行一条独立可执行的 JSON |
| `run_stability_regress.py` | 离线运行器：路由/上下文/画像/终止/故障五轴断言 + 三道门禁 |
| `../ai-service/tests/test_chat_stability_regress.py` | pytest 回归（12 个用例，含 mock Tutor 端到端） |

## 数据模式

每行字段（在 chat_foundation_v1 字段基础上扩展断言轴，均为机器可判定）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` / `category` / `turns` / `current_message` / `evaluator_notes` | — | 同 chat_foundation_v1 口径 |
| `expected_route` | string | `NORMAL_CHAT / PLAN / RESOURCE / EXERCISE / VISUALIZATION` |
| `expected_task_mode` | string | 首任务模式：普通问答 `auto`、空输入 `inquiry`、能力类对应编排中心 |
| `expected_terminal` | string | SSE 终止合同：`done`（健康/inquiry）或 `error`（降级场景） |
| `expect_content` | bool | 用户是否应看到非空回答内容 |
| `expect_history_in_context` | bool | 二轮场景：上一轮必须出现在任务上下文与 BuiltContext 中 |
| `expected_context_turn_count` | int | 路由审计的 `context_turn_count` 期望值 |
| `expected_history_anchors` | array[str] | 上一轮正文中必须可达的锚点子串 |
| `profile_facts_forbidden` / `profile_facts_required` | array[str] | 画像注入断言：无关字段不得注入 / 塑形字段保留 |
| `fault` | object | 故障注入脚本：`kind=sanity`（answers 序列 + 期望裁决）或 `kind=terminal_error` |
| `must_not_include` | array[str] | 用户可见文本不得包含的内部泄露标记 / 异常细节 |

## 类别构成（19 条）

| category | 数量 | 考什么 |
|---|---|---|
| `concept_qa`（cq-） | 2 | 单轮概念解释（进程 / 虚拟内存） |
| `compare_qa`（cp-） | 1 | 比较型问题（"区别"不得误当对比图请求） |
| `study_advice`（sa-） | 1 | 学习建议（不得误触发计划生成） |
| `followup_2turn`（fw-） | 3 | 二轮追问 / 纠正：历史接线 + 当前消息恒在末位 |
| `capability_request`（cr-） | 4 | 明确资源/练习/图解/计划请求进入对应编排中心 |
| `noise_robustness`（nr-） | 4 | 模糊寒暄、名词陷阱（"知识图谱是什么？"）、无关画像、空输入 |
| `fault_injection`（fi-） | 4 | 空回答重试恢复 / 连续空回答降级 / 内部泄露拦截 / 错误终态可观测 |

## 运行命令

```bash
# ① 离线回归运行器（项目根目录或 ai-service 目录均可；报告写入 evals/reports/）
python evals/run_stability_regress.py
python evals/run_stability_regress.py --no-write   # 只看摘要

# ② pytest 回归（ai-service 目录）
python -m pytest tests/test_chat_stability_regress.py -v

# ③ 数据标定复查（守门：expected_route 与 CapabilityGate 零分歧）
python evals/verify_routes.py                      # chat_foundation_v1（60 条）
```

运行器零网络、零 LLM：路由来自真实 `CapabilityGate`，上下文来自真实
`ContextBuilder`，重试编排来自生产 `run_with_sanity_check`，端到端走
`TutorAgent(use_mock_llm=True)`。任何改动后先跑 ①②，秒级反馈。

## 门禁（任一不达标退出码 1）

| 门禁 | 期望 |
|---|---|
| `route_calibration_zero_divergence` | 19 条标定与 CapabilityGate 零分歧 |
| `all_cases_pass` | 全部样例五轴断言通过 |
| `degradation_always_detected` | 健康样例在流退化（error 终止）时必须被终止合同发现 |

## 维护规则

- v1 冻结：不改写、不追加；新增场景走 `chat_stability_v2.jsonl`，保证回归可比。
- 标定与 CapabilityGate 出现分歧时先人工裁决：措辞歧义改数据，门控缺陷回 Task 4。
- 端到端用例依赖 `TutorAgent(use_mock_llm=True)`；真实 LLM 质量评审归 Task 11 的
  chat_foundation 60 条 + 人工抽检，不在本套件范围。

## 实战记录

- 2026-09-06：套件首跑即抓到工作区未提交改动在 `AutoCenter._run_tutor`
  （auto_center.py:84）引用未定义 `context` 的 NameError——该缺陷会让所有普通聊天
  返回"答疑失败"（异常被 except 吞掉、SSE 层表现为错误终态）。该行当日被修正为
  `(task.context or {}).get("conversation_id")`，pytest 端到端用例转绿并长期守护该接线。
