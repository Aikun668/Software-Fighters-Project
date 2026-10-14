# Stage 0.2 交接报告（测试数据集构建）

> **阶段**：Stage 0.2 · 测试数据集构建
> **产出人**：Coding Agent A（Python AI 服务）
> **日期**：2026-10-13
> **状态**：✅ 完成，按约束**停止**（未进入 Stage 0.3、未运行旧路由准确率评测、未改 CapabilityGate / RouterAgent）
> **基线**：commit `24dd24d` + 工作区哈希（见 `baseline_workspace_record.md`），9 个路由核心文件哈希**逐一复核一致**。

---

## 一、交付物清单（全在 `docs/agent-engineering/routing-baseline/`）

| 交付物 | 对应任务 | 说明 |
|---|---|---|
| `baseline_workspace_record.md` | 决策 1 | 候选测试基线（HEAD + 未提交改动 + SHA-256） |
| `routing_related_uncommitted.diff` | 决策 1 | 路由相关未提交改动原文（129 行） |
| `intent_reachability.md` | 任务 A | 11 条意图可达性核查（机制证据） |
| `probe_intent_reachability.py` | 任务 A | 只读探针（走真实入口 `ChatCenter.route()`） |
| `routing_cases.jsonl` | 任务 B+C | 140 条测试用例（统一结构） |
| `routing_cases_review.csv` | 任务 C+D | 140 条评审表（含 suggested_* 初步建议） |
| `build_routing_review.py` | 任务 C | CSV 生成器（不导入路由代码，纯人工建议编码） |
| `routing_policy_questions.md` | 任务 D | 策略问题清单（A 能力缺口 / B 算法判断 / C 产品决策） |

---

## 二、10 条验收标准逐一核对（全部 ✅）

| # | 标准 | 结果 |
|---|---|---|
| 1 | 恰好 140 条唯一 ID | ✅ 140 唯一，无重复 |
| 2 | JSONL 有效 | ✅ 逐行 `json.loads` 通过 |
| 3 | 12 类计数与设定一致 | ✅ 12 类合计 140 |
| 4 | 11 意图独立覆盖统计 | ✅ 11/11 全覆盖（`suggested_intents` 列） |
| 5 | 多轮样本含上文 | ✅ 20 案 `history` 均非空 |
| 6 | ≥10 条显式 mode | ✅ 12 条（exercise/resource/plan/visualization 各 3） |
| 7 | 真实数据脱敏 | ✅ 仓库无真实语料 → **全部人工构造并诚实标注**（`source_type=人工构造`） |
| 8 | 无 Agent 建议当作已审答案 | ✅ `label_status=待人工审核`、`reviewer_decision` 全空 |
| 9 | 路由源未修改 | ✅ 9 文件 SHA-256 与基线逐一比对一致 |
| 10 | 每案可按 Case ID 定位 | ✅ JSONL 与 CSV 的 ID 集合完全一致 |

---

## 三、类别分布（12 类，合计 140）

| 类别 | 条数 |
|---|---|
| 普通概念答疑 | 15 |
| 解答已有题目 | 10 |
| 明确生成练习题 | 15 |
| 明确生成学习资源 | 10 |
| 学习规划 | 10 |
| 可视化 | 10 |
| 诊断与画像相关 | 10 |
| 隐式需求非标准表达 | 15 |
| 多轮上下文与指代 | 20 |
| 复合任务 | 15 |
| 否定表达引用内容干扰 | 5 |
| 空输入模糊请求缺少参数 | 5 |

---

## 四、核心发现（供 Stage 1 方案评审）

1. **【能力缺口 · 最重要】** 4 条 `center=auto` 意图中 3 条（`solve_problem`/`diagnose`/`profile_building`）**无一级能力入口**，干净单意图表达系统性落 `tutor_question`；`code_example` 亦无专属规则。**这不是打分失误，是产品未赋予能力槽位**——Stage 1 若只调二级权重不会改善。
2. **【单点咽喉】** 一级 `CapabilityGate` 是全链路单点：二级只在 gate 判非 `NORMAL_CHAT` 时才运行（`chat_center.py:170` 早返回 / `:197` 进二级）。
3. **【兜底覆盖】** gate 权威兜底（`chat_center.py:204-214`）在 expected_center 缺席时**整体重建计划、丢弃二级产出**，是「条件可达」意图的第二重脆弱点。
4. **【互斥误伤】** `{solve_problem, exercise_gen}` 互斥组会吞掉 `solve_problem`（顺序共现场景下为误伤）。
5. **【漏检】** `request_material` 动词白名单不含「做」，`做几张记忆卡` 被判 NORMAL_CHAT。
6. **【阈值】** `diagnose` 单关键词命中（0.5×0.8=0.4）过不了 `_CONFIDENCE_THRESHOLD=0.4`，需 ≥2 命中。

> 发现 1 归属「产品能力缺口」；发现 3–6 归属「路由算法判断」。详见 `routing_policy_questions.md` §0 三类定义与 §4 归属表。

---

## 五、约束遵守声明

- ✅ **未提交 / 未暂存 / 未还原 / 未覆盖**任何已有改动（决策 1）。
- ✅ **未运行旧路由准确率评测**；探针仅走 `route()`（无 LLM/IO），不产生生成任务。
- ✅ **未修改** `CapabilityGate` / `RouterAgent` / 任何路由逻辑。
- ✅ 测试集**独立于旧路由预测**设计：`build_routing_review.py` 不导入任何 ai-service 路由代码，`suggested_*` 来自对「学生真实诉求」的人工判断。
- ✅ 未进入 Stage 0.3 / Stage 1。

---

## 六、阻碍与缺口

- **无技术阻碍**。
- **唯一缺口**：仓库内**不存在真实学生对话语料**，故 140 条**全部**为人工构造（原任务目标「≤~60 真实脱敏 + 其余人工」中的真实部分为 **0**）。已按「不得编造真实来源」要求**诚实标注** `source_type=人工构造`。若后续能提供脱敏真实语料，建议增设 batch 2 与其对照。

---

## 七、对外可转发摘要（Externally Forwardable Summary）

> **Stage 0.2 完成**。已交付 140 条独立设计的路由测试用例（12 类，覆盖全部 11 条注册意图，含 12 条显式 mode、20 条多轮、15 条复合任务），配套只读探针、评审 CSV（含初步建议）、策略问题清单，及工作区 SHA-256 基线。**通过全部 10 条验收标准**。
>
> **关键结论**：`solve_problem` / `diagnose` / `profile_building` / `code_example` 四条意图因**一级无能力入口**而无法由自然表达到达（属**产品能力缺口**，非算法 bug）；另有否定识别、互斥误伤、动词白名单漏检等 **5 项算法层**问题。建议 Stage 1 **先由产品/架构师裁决 A 类缺口与 C 类澄清策略**，再规划 gate/router 改动。
>
> **未做**：未运行旧路由准确率评测、未改任何路由代码、未进入 Stage 0.3。**待指示**。

---

## 八、下一步（等待指令，不自行开始）

1. 人工审核 `routing_cases_review.csv`（填 `reviewer_decision`，裁决 `policy_question`）。
2. 外部架构师评审 `routing_policy_questions.md`，对 A1–A4 / C-1–C-3 定调。
3. 经明确批准后方可进入 Stage 0.3（旧路由基准评测）。
