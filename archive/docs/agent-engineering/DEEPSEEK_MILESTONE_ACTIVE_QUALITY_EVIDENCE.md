# DeepSeek Harness 阶段任务书：主动修复与真实证据闭环

## 任务定位

你是实施工程师。本阶段不是新增一套 Agent 架构，而是把已实现的资源质量门控从“Shadow 模式下可观察”推进到“Active 模式下可验证”，为是否启用生产主动修复提供证据。

完成本阶段后，Codex 将基于证据决定是否把默认 `quality_mode` 从 `shadow` 调整为 `active`；**你不得自行修改该默认值。**

## 必读上下文

按以下顺序阅读；本文是当前执行范围的最高优先级交接文件。

1. `AGENTS.md`
2. `docs/agent-engineering/PRINCIPLES.md`
3. `docs/superpowers/specs/2026-08-14-resource-workflow-agent-engineering-design.md`
4. `docs/superpowers/plans/2026-08-14-resource-workflow-quality-gate.md`
5. `docs/agent-engineering/resource-workflow-evidence-template.md`
6. 当前分支最近提交及工作区未提交变更。

已知基线：默认生产模式为 `shadow`；Judge 使用 `PROFILE_REVIEW`（temperature 0）；真实运行证据与完整 artifact 均位于 Git 忽略的 `ai-service/temp_file/evidence/`。

## 阶段目标

证明下列 Repair 语义在 `content` 与 `interactive_diagram` 的实际调用链中成立，并完成一轮可复核的真实 `active` 运行：

```text
生成草稿 → Validator → Judge=repair
  → 将“修复建议 + 修复前草稿”交给同一 Specialist
  → 最多一次修复 → 再校验 → 保留最终结果与前后证据
```

这里的“证明”包括强制触发 Repair 的自动化测试，以及真实模型的运行记录；不能仅凭代码阅读或一次恰好 Judge=pass 的运行下结论。

## 完成范围与硬边界

### 必须达成

1. Repair 对所有已纳入质量门控、实际可路由的 `content` 子路径和 `interactive_diagram` 生效。任何路径不得在收到 `repair_instructions` 后静默忽略它们；若某个子路径无法合理修复，必须显式降级或排除，并在结果中说明原因与影响。
2. Repair 前草稿必须在成功、校验失败和 Specialist 异常三类分支中保留为 `pre_repair_blocks`，以便 runner 写出前后 artifact。
3. 每次请求最多一次 Repair。Repair 异常或二次校验失败时保留原始、已通过基础 Validator 的草稿，不把 Judge 的非致命意见升级成整条请求失败。
4. 在 mock/测试环境中强制 Judge 返回 `repair`，验证：修复建议与旧草稿确实进入 Specialist 的实际 Prompt；最终产物来自修复调用；前后 artifact 可被 runner 保存。
5. 以真实 DeepSeek 配置运行固定 6 案例的 `active` 轮次，并记录每个案例的状态、耗时和 artifact 路径。真实运行不提交 API Key、原始模型回复、日志或 artifact。
6. 更新人工证据模板，明确区分：自动化强制 Repair 证据、真实 active 运行事实、人工结论、已知限制。

### 不在本阶段

- 不修改默认 `quality_mode`，不修改 LLM Provider、模型配置或密钥。
- 不修改 content safety filter / SafetyPipeline 规则；不把已有 `violence` 日志推断为 Repair 的原因。
- 不重构 Router、ResultAgent、ResourceCenter、SSE 协议或前端页面。
- 不扩展新的资源类型、记忆、RAG、多 Agent 编排或多次重试。
- 不提交 `temp_file/evidence/`、日志、`.env` 或任何密钥。

## 交付物

1. 最小必要的实现与测试；保持当前模块边界：Agent 负责消费 Repair 上下文，Workflow 负责一次性控制与状态/证据保留，Runner 负责落盘证据。
2. 小粒度 Git 提交，提交信息能说明行为变化。
3. `docs/agent-engineering/resource-workflow-evidence-template.md` 的本轮结论更新。
4. 一份最终交接报告，使用下方格式。

## 验收标准

### 自动化验收

- `content`（含所有实际可路由子路径）和 `interactive_diagram` 的强制 `repair` 测试均证明实际 Prompt 含修复建议和旧草稿。
- Specialist 修复成功时：`repair_attempted=True`、调用次数严格为首次生成 + 一次修复、`pre_repair_blocks` 与最终 `content_blocks` 可区分。
- Specialist 修复异常或二次校验失败时：仍有 `pre_repair_blocks`，最终交付为原始合法草稿，不超过一次 Repair。
- Runner 对发生 Repair 的结果保存 `<case_id>.pre-repair.json` 与最终 artifact；未发生 Repair 不伪造前置 artifact。
- 至少通过：

```powershell
cd ai-service
pytest tests/test_repair_semantics.py tests/test_resource_gen_quality_flow.py tests/test_resource_quality_gate.py tests/test_resource_workflow_evidence_runner.py tests/test_e2e_resource_workshop.py -v
python -m compileall -q app scripts tests
```

如涉及前端配置或组件，额外执行受影响的前端测试与 type-check；无关代码不扩测。

### 真实运行验收

在 API 配置有效时运行：

```powershell
cd ai-service
python scripts/run_resource_workflow_cases.py --mode real --quality-mode active --output temp_file/evidence/active-real-v1.jsonl
```

- 固定 6 案例均有 JSONL 记录；记录必须包含 `review_status`、`review_reason`、`repair_attempted`、`pre_repair_artifact_path`、`artifact_path`、`final_status`、`elapsed_ms`。
- 若真实 Judge 没有给出 `repair`，该结果只说明 active 路径未破坏通过案例；强制 Repair 测试仍是 Repair 语义的主要自动化证据。
- 若真实 Repair 发生，人工比较 pre/post artifact：修复后应仍通过结构校验、主题不偏移、没有无意义重写；记录是否改善或退化。
- 若真实运行被供应商/网络阻塞，保留错误类型和已完成案例，完成自动化验收后报告阻塞；不得伪造真实证据。

## 提交与报告要求

实施前先检查工作区。若存在与本阶段相关的未提交改动，先验证、补测试并把它们纳入本阶段提交；不得覆盖或删除其他未跟踪 artifact。

完成后一次性向 Codex 报告：

```text
阶段状态：完成 / 部分完成（真实运行阻塞） / 阻塞
提交：<hash> <message>；...
改动文件：...

Repair 语义：
- content 覆盖的子路径：...
- diagram：...
- 异常与二次校验失败时的保留行为：...

自动化验证：
- <命令> → <通过数/跳过数/耗时>

真实 active 证据：
- 输出 JSONL：...
- 6 例汇总：pass / repair / skipped、实际 repair 次数、fallback 次数、失败数、耗时范围
- 若发生 repair：case_id、pre/post artifact 路径、人工比较结论

证据模板更新：<文件与摘要>
是否建议切换默认 active：建议 / 暂不建议
理由与已知限制：...
需要 Codex 决策：无 / ...
```

## Codex 决策门槛

只有同时满足以下条件，才可建议 Codex 考虑切换默认 `active`：

1. 所有自动化验收通过，且强制 Repair 与异常保留分支都有覆盖；
2. 真实 6 案例没有出现由质量门控引入的未处理错误或重复 Repair；
3. 若发生真实 Repair，人工确认结果未退化；
4. 证据模板的结论与 JSONL/artifact 一致。

不满足任一条件时，默认结论是继续维持 `shadow`，并将事实、最小复现和候选方案交给 Codex 决策。
