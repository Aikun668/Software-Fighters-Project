# Resource Workflow Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为资源生成 Workflow 增加可观测的确定性校验、轻量 LLM Judge、一次修复、可靠 SSE 回退和可复现的反馈闭环。

**Architecture:** 保持 `RouterAgent → ResultAgent → ResourceCenter → ResourceGenWorkflow` 的外层边界不变。质量门控收敛在资源生成 Workflow 内：Validator 负责硬约束，Judge 只输出 `pass | repair | skipped`，Repair 最多一次；同一批固定案例先以 Shadow 模式运行，再开启修复并比较运行记录。

**Tech Stack:** Python 3.11、FastAPI、LangGraph、Pydantic、pytest/pytest-asyncio、现有 SSE `StreamEvent`、现有 LLM 服务与 YAML Prompt 加载器。

## Global Constraints

- 不增加第三方依赖，不重写 RouterAgent、ResultAgent、Center 或前端 SSE 协议。
- 第一版只对 `content` 与 `interactive_diagram` 启用 LLM Judge；其余四类资源保持当前生成路径。
- Judge 不做五维打分，不作为事实验证器；只能返回 `pass`、`repair` 或在故障时 `skipped`。
- Validator 失败的内容不能直接交付；Judge 的主观 `repair` 不能丢弃已通过 Validator 的内容。
- 每个请求最多执行一次 Repair；所有执行路径最多发送一个最终 `done` 事件。
- 原始真实模型输出写入受 Git 忽略的证据目录；只提交案例定义、脚本、测试和人工整理结论。

---

## 文件结构

- Create: `ai-service/app/services/resource_quality_gate.py` — Validator、Judge 契约与 LLM 调用封装。
- Modify: `ai-service/prompts/tutor_agent/resource_judge.yaml` — 改为 `pass | repair` 的资源 Judge Prompt。
- Modify: `ai-service/prompts/tutor_agent/visualize_judge.yaml` — 改为 `pass | repair` 的图解 Judge Prompt。
- Modify: `ai-service/app/workflows/resource_gen.py` — State、LangGraph 节点、条件边、修复/降级和事件。
- Modify: `ai-service/internal_api.py` — 在 `done` payload 中透传安全的运行状态字段。
- Modify: `ai-service/.gitignore` — 忽略 `temp_file/evidence/` 的原始运行记录。
- Create: `ai-service/tests/test_resource_quality_gate.py` — Validator 与 Judge 契约测试。
- Create: `ai-service/tests/test_resource_gen_quality_flow.py` — Workflow 状态转换与事件测试。
- Create: `ai-service/tests/test_resource_workflow_evidence_runner.py` — JSONL 运行记录构造测试。
- Modify: `ai-service/tests/test_e2e_resource_workshop.py` — SSE 对外契约测试。
- Create: `ai-service/tests/fixtures/resource_workflow_cases.json` — 6 个固定案例。
- Create: `ai-service/scripts/run_resource_workflow_cases.py` — 运行案例并产出 JSONL 证据。
- Create: `docs/agent-engineering/resource-workflow-evidence-template.md` — 人工复核与前后对比模板。

## Task 1: 建立质量门控契约与确定性 Validator

**Files:**

- Create: `ai-service/app/services/resource_quality_gate.py`
- Create: `ai-service/tests/test_resource_quality_gate.py`

**Interfaces:**

- Produces `ValidationResult(passed: bool, reason: str, issues: list[str])`。
- Produces `ReviewDecision(status: Literal["pass", "repair", "skipped"], reason: str, fixes: list[str])`。
- Produces `ResourceValidator.validate(resource_type: str, content_blocks: list[dict]) -> ValidationResult`；Workflow 调用时传入 Director 的 `agent_name`（如 `content`），不直接使用前端的宽泛 `resource_type`（如 `document`）。

- [ ] **Step 1: 写出 `content` 的失败测试**

```python
from app.services.resource_quality_gate import ResourceValidator

def test_content_validator_rejects_empty_blocks():
    result = ResourceValidator().validate("content", [])
    assert result.passed is False
    assert result.issues == ["content_blocks 不能为空"]

def test_content_validator_accepts_section_with_heading_and_content():
    blocks = [{"type": "section", "heading": "反向传播", "content": "用于计算梯度。"}]
    result = ResourceValidator().validate("content", blocks)
    assert result.passed is True
```

- [ ] **Step 2: 运行失败测试，确认契约不存在**

Run: `pytest tests/test_resource_quality_gate.py -v`

Expected: FAIL，提示 `app.services.resource_quality_gate` 或 `ResourceValidator` 不存在。

- [ ] **Step 3: 写出 `interactive_diagram` 的失败测试**

```python
def test_diagram_validator_rejects_wrong_block_type():
    blocks = [{"type": "section", "heading": "CNN", "content": "文本"}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is False
    assert "interactive_diagram" in result.reason

def test_diagram_validator_accepts_renderable_block():
    blocks = [{"type": "interactive_diagram", "heading": "CNN", "content": "<svg></svg>"}]
    result = ResourceValidator().validate("interactive_diagram", blocks)
    assert result.passed is True
```

- [ ] **Step 4: 实现最小 Validator 和不可变结果类型**

```python
@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)

class ResourceValidator:
    def validate(self, resource_type: str, content_blocks: list[dict]) -> ValidationResult:
        if not content_blocks:
            return ValidationResult(False, "content_blocks 不能为空", ["content_blocks 不能为空"])
        if resource_type == "content":
            valid = any(
                block.get("type") == "section"
                and bool(str(block.get("heading", "")).strip())
                and bool(str(block.get("content", "")).strip())
                for block in content_blocks
            )
            return ValidationResult(valid, "" if valid else "缺少完整 section 内容块")
        if resource_type == "interactive_diagram":
            valid = any(
                block.get("type") == "interactive_diagram"
                and bool(str(block.get("content", "")).strip())
                for block in content_blocks
            )
            return ValidationResult(valid, "" if valid else "缺少 interactive_diagram 内容块")
        return ValidationResult(True)
```

- [ ] **Step 5: 运行 Validator 测试并提交**

Run: `pytest tests/test_resource_quality_gate.py -v`

Expected: PASS。

```bash
git add app/services/resource_quality_gate.py tests/test_resource_quality_gate.py
git commit -m "feat: add resource output validator"
```

## Task 2: 接入轻量 LLM Judge，并先以 Shadow 模式调用

**Files:**

- Modify: `ai-service/app/services/resource_quality_gate.py`
- Modify: `ai-service/prompts/tutor_agent/resource_judge.yaml`
- Modify: `ai-service/prompts/tutor_agent/visualize_judge.yaml`
- Modify: `ai-service/tests/test_resource_quality_gate.py`

**Interfaces:**

- Produces `ResourceReviewService.review(topic, resource_type, content_blocks, student_profile) -> ReviewDecision`。
- `ReviewDecision.status` 只能是 `pass`、`repair`、`skipped`。
- Judge 异常或无法解析 JSON 时必须返回 `skipped`，不抛出异常。

- [ ] **Step 1: 写出 Judge 标准化失败测试**

```python
@pytest.mark.asyncio
async def test_review_service_normalizes_repair_and_limits_fixes():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value='{"decision":"repair","reason":"缺少步骤","fixes":["补充目标", "补充示例", "补充总结", "忽略这条"]}')
    result = await service.review("反向传播", "content", [{"type": "section", "heading": "概念", "content": "..."}], {})
    assert result.status == "repair"
    assert result.fixes == ["补充目标", "补充示例", "补充总结"]

@pytest.mark.asyncio
async def test_review_service_returns_skipped_on_invalid_json():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value="not json")
    result = await service.review("CNN", "interactive_diagram", [{"type": "interactive_diagram", "content": "<svg/>"}], {})
    assert result.status == "skipped"

@pytest.mark.asyncio
async def test_review_service_normalizes_unknown_decision_to_pass():
    service = ResourceReviewService(use_mock=True)
    service._chat = AsyncMock(return_value='{"decision":"unknown","reason":"ok","fixes":[]}')
    result = await service.review("CNN", "content", [{"type": "section", "heading": "概念", "content": "..."}], {})
    assert result.status == "pass"
```

- [ ] **Step 2: 运行测试，确认 Judge 服务尚未实现**

Run: `pytest tests/test_resource_quality_gate.py -v`

Expected: FAIL，提示 `ResourceReviewService` 不存在。

- [ ] **Step 3: 将两个 YAML Prompt 收缩为三字段 JSON 契约**

两个 Prompt 均要求仅返回：

```json
{
  "decision": "pass 或 repair",
  "reason": "不超过 60 字的中文原因",
  "fixes": ["最多三条具体修复建议"]
}
```

`resource_judge.yaml` 只判断主题匹配、最低学习可用性和明显结构问题；`visualize_judge.yaml` 只判断图解是否表达主题、标签可读和明显不可用问题。删除五维分数、总分和阈值要求。

- [ ] **Step 4: 实现 Judge 服务**

```python
class ResourceReviewService:
    def __init__(self, use_mock: bool = False, llm=None):
        self.use_mock = use_mock
        self._llm = llm

    async def review(self, topic, resource_type, content_blocks, student_profile) -> ReviewDecision:
        if resource_type not in {"content", "interactive_diagram"}:
            return ReviewDecision("skipped", "该资源类型未启用 Judge")
        try:
            raw = await self._chat(topic, resource_type, content_blocks, student_profile)
            data = parse_llm_json(raw, fallback={})
            decision = "repair" if data.get("decision") == "repair" else "pass"
            fixes = [str(item) for item in data.get("fixes", [])[:3] if str(item).strip()]
            return ReviewDecision(decision, str(data.get("reason", ""))[:60], fixes)
        except Exception:
            return ReviewDecision("skipped", "Judge 不可用")
```

`_chat` 使用现有 `create_llm`、`build_prompt("tutor_agent", ...)` 和 `parse_llm_json`；根据资源类型选择两份已有 YAML。

- [ ] **Step 5: 运行 Judge 测试并提交**

Run: `pytest tests/test_resource_quality_gate.py -v`

Expected: PASS，包含 `pass`、`repair`、`skipped` 三种状态。

```bash
git add app/services/resource_quality_gate.py prompts/tutor_agent/resource_judge.yaml prompts/tutor_agent/visualize_judge.yaml tests/test_resource_quality_gate.py
git commit -m "feat: add lightweight resource judge"
```

## Task 3: 将质量门控接入 ResourceGenWorkflow

**Files:**

- Modify: `ai-service/app/workflows/resource_gen.py`
- Create: `ai-service/tests/test_resource_gen_quality_flow.py`

**Interfaces:**

- `ResourceGenWorkflow.__init__(..., validator=None, reviewer=None, quality_mode="active")` 支持测试注入；`quality_mode` 只能为 `off`、`shadow`、`active`。
- `off` 完全跳过质量门控，用于行为等价基线；`shadow` 记录 Validator/Judge 结论但绝不触发 Repair 或质量降级；`active` 执行一次 Repair 与结构性失败降级。
- State 新增 `draft_blocks`、`validation_result`、`review_status`、`review_reason`、`repair_instructions`、`repair_attempted`、`fallback_used`、`final_status`、`stage_timings`。
- Node 名称固定为 `validate`、`review`、`repair`、`fallback`。

- [ ] **Step 1: 写出状态机分支失败测试**

```python
@pytest.mark.asyncio
async def test_passed_review_finalizes_without_repair():
    workflow = build_workflow_with_fake_services(review_status="pass")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "pass"
    assert result["repair_attempted"] is False
    assert result["final_status"] == "success"

@pytest.mark.asyncio
async def test_repair_runs_once_then_delivers_valid_output():
    workflow = build_workflow_with_fake_services(review_status="repair")
    result = await workflow.run(valid_content_state())
    assert result["repair_attempted"] is True
    assert result["final_status"] == "success"

@pytest.mark.asyncio
async def test_skipped_review_does_not_block_valid_output():
    workflow = build_workflow_with_fake_services(review_status="skipped")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "skipped"
    assert result["content_blocks"]

@pytest.mark.asyncio
async def test_shadow_mode_records_repair_without_changing_output():
    workflow = build_workflow_with_fake_services(review_status="repair", quality_mode="shadow")
    result = await workflow.run(valid_content_state())
    assert result["review_status"] == "repair"
    assert result["repair_attempted"] is False
    assert result["final_status"] == "success"
```

- [ ] **Step 2: 运行测试，确认新 State 和节点尚不存在**

Run: `pytest tests/test_resource_gen_quality_flow.py -v`

Expected: FAIL，提示构造辅助函数或质量字段不存在。

- [ ] **Step 3: 重构生成逻辑以复用 Specialist 调用**

在 `ResourceGenWorkflow` 中新增私有方法：

```python
async def _run_specialist(self, state: ResourceGenState, agent_name: str, repair_instructions: list[str] | None = None) -> dict:
    """构建 Agent state，必要时附加修复说明，并标准化 blocks/response。"""
```

`_generate_node` 调用该方法并把结果写入 `draft_blocks`；`_repair_node` 复用该方法，传入 `repair_instructions`，然后将 `repair_attempted=True`。Validator/Judge 都使用 `state["agent_name"]` 作为质量门控的资源类型；未在首版范围内的 Agent 直接得到 `not_applicable`，保持原生成路径。

同时以单一帮助方法记录阶段耗时，避免各节点各自拼装字段：

```python
def _with_stage_timing(self, state: ResourceGenState, stage: str, started_at: float, update: dict) -> dict:
    timings = dict(state.get("stage_timings", {}))
    timings[stage] = round((time.perf_counter() - started_at) * 1000, 2)
    return {**update, "stage_timings": timings}
```

`plan`、`generate`、`validate`、`review`、`repair`、`fallback` 节点都通过该方法返回状态更新。

- [ ] **Step 4: 为图添加节点与条件边**

```python
graph.add_node("validate", self._validate_node)
graph.add_node("review", self._review_node)
graph.add_node("repair", self._repair_node)
graph.add_node("fallback", self._fallback_node)

graph.add_edge("generate", "validate")
graph.add_conditional_edges("validate", self._after_validate, {
    "review": "review", "repair": "repair", "fallback": "fallback",
})
graph.add_conditional_edges("review", self._after_review, {
    "repair": "repair", "finalize": "finalize",
})
graph.add_edge("repair", "validate")
graph.add_edge("fallback", "finalize")
```

`_after_validate` 在 `active` 模式的第一次结构失败时选择 `repair`，二次结构失败时选择 `fallback`；`shadow` 模式记录结果后继续 `review`，`off` 模式直接 `finalize`。`_after_review` 仅当模式为 `active` 且 `status == "repair" and not repair_attempted` 时选择 `repair`；其他模式和其他状态都进入 `finalize`。

- [ ] **Step 5: 实现降级与最终状态**

`_fallback_node` 对非 `content` Specialist 调用现有 ContentAgent；若 ContentAgent 也无法生成可通过 Validator 的内容，则写入 `final_status="error"` 与用户可读 `error`。`_finalize_node` 将 `draft_blocks` 或降级结果固化为 `content_blocks`，并仅在 `final_status` 未设置时写入 `success`。

- [ ] **Step 6: 运行专项与既有资源测试并提交**

Run: `pytest tests/test_resource_gen_quality_flow.py tests/test_e2e_resource_workshop.py -v`

Expected: PASS；六类原有路由测试不回退。

```bash
git add app/workflows/resource_gen.py tests/test_resource_gen_quality_flow.py
git commit -m "feat: add bounded resource review workflow"
```

## Task 4: 对齐 SSE 完成语义与外部状态

**Files:**

- Modify: `ai-service/internal_api.py`
- Modify: `ai-service/tests/test_e2e_resource_workshop.py`

**Interfaces:**

- `done` 事件增加可选字段：`review_status`、`repair_attempted`、`fallback_used`、`final_status`。
- 所有非致命 Judge 状态仍返回 HTTP 200、一个 `done`，且不发送 `error` SSE。

- [ ] **Step 1: 写出 SSE 契约失败测试**

```python
@pytest.mark.asyncio
async def test_sse_done_contains_review_metadata(async_client):
    output = {
        **_mock_workflow_output("content"),
        "review_status": "skipped",
        "repair_attempted": False,
        "fallback_used": False,
        "final_status": "success",
    }
    # 使用现有 _get_resource_workflow patch 发起请求
    # 断言唯一 done event 的 data 含四个字段

@pytest.mark.asyncio
async def test_sse_skipped_review_is_not_error(async_client):
    # 使用 review_status="skipped" 的 workflow mock
    # 断言事件中没有 type="error"，且 done 恰好一次
```

- [ ] **Step 2: 运行测试，确认 done payload 尚未透传字段**

Run: `pytest tests/test_e2e_resource_workshop.py -v -k "review_metadata or skipped_review"`

Expected: FAIL，提示 `review_status` 等字段缺失。

- [ ] **Step 3: 扩展两个资源 SSE 入口的 done payload**

在 `/resources/generate` 与 `/inquiry/resolve` 的 `done_event` payload 中加入：

```python
"review_status": state.get("review_status", "not_applicable"),
"repair_attempted": state.get("repair_attempted", False),
"fallback_used": state.get("fallback_used", False),
"final_status": state.get("final_status", "success"),
```

不新增 SSE 类型；`review`、`repair`、`fallback` 仅作为现有 `stage_start` 与 `stage_end` 的 `stage` 值。

- [ ] **Step 4: 运行 SSE 与资源回归测试并提交**

Run: `pytest tests/test_e2e_resource_workshop.py -v`

Expected: PASS；每条请求只有一个 `done`。

```bash
git add internal_api.py tests/test_e2e_resource_workshop.py
git commit -m "feat: expose resource workflow review status"
```

## Task 5: 建立固定案例、Shadow 记录与人工对比证据

**Files:**

- Modify: `ai-service/.gitignore`
- Create: `ai-service/tests/fixtures/resource_workflow_cases.json`
- Create: `ai-service/scripts/run_resource_workflow_cases.py`
- Create: `docs/agent-engineering/resource-workflow-evidence-template.md`
- Test: `ai-service/tests/test_resource_quality_gate.py`

**Interfaces:**

- 案例文件包含 6 条记录，每条具有 `case_id`、`topic`、`resource_type`、`student_profile`、`expected_block_type`。
- Runner 参数为 `--mode mock|real`、`--quality-mode off|shadow|active` 与 `--output <jsonl-path>`。
- Runner 每行输出规格中定义的最小运行记录字段。

- [ ] **Step 1: 写 6 个固定案例**

- `content` 案例：Transformer 自注意力原理、CNN 与 RNN 对比、反向传播入门学习资料。
- `interactive_diagram` 案例：CNN 架构、反向传播流程、注意力机制数据流。

每个案例使用固定的简化画像，例如：

```json
{
  "case_id": "content-transformer-basics",
  "topic": "面向初学者解释 Transformer 自注意力机制",
  "resource_type": "document",
  "student_profile": {"knowledge_base": 30, "cognitive_style": "visual"},
  "expected_block_type": "section"
}
```

- [ ] **Step 2: 写 Runner 单元测试**

在 `tests/test_resource_workflow_evidence_runner.py` 中写：

```python
def test_record_contains_all_required_fields():
    record = build_run_record(case_id="case-1", state={"agent_name": "content"}, elapsed_ms=12)
    assert set(record) >= {
        "case_id", "run_id", "workflow_version", "route_agent", "route_strategy",
        "stage_timings", "validation_result", "review_status", "repair_attempted",
        "fallback_used", "final_status", "error_type",
    }
```

- [ ] **Step 3: 实现 JSONL Runner 与忽略规则**

```python
def build_run_record(case_id: str, state: dict, elapsed_ms: int) -> dict:
    return {
        "case_id": case_id,
        "run_id": state.get("run_id", ""),
        "workflow_version": "resource-quality-gate-v1",
        "route_agent": state.get("agent_name", ""),
        "route_strategy": state.get("route_strategy", ""),
        "stage_timings": state.get("stage_timings", {}),
        "validation_result": state.get("validation_result", {}),
        "review_status": state.get("review_status", "not_applicable"),
        "repair_attempted": state.get("repair_attempted", False),
        "fallback_used": state.get("fallback_used", False),
        "final_status": state.get("final_status", ""),
        "error_type": state.get("error_type", ""),
        "elapsed_ms": elapsed_ms,
    }
```

将 `temp_file/evidence/` 添加到 `ai-service/.gitignore`。Runner 默认输出到该目录，真实输出不提交。

- [ ] **Step 4: 执行三轮证据运行**

```bash
python scripts/run_resource_workflow_cases.py --mode mock --quality-mode off --output temp_file/evidence/baseline-mock.jsonl
python scripts/run_resource_workflow_cases.py --mode mock --quality-mode shadow --output temp_file/evidence/shadow-mock.jsonl
python scripts/run_resource_workflow_cases.py --mode real --quality-mode active --output temp_file/evidence/active-real.jsonl
```

第一轮的 `off` 是与改造前等价的基线；第二轮 `shadow` 会记录判断但不会改变最终产物；第三轮只在人工确认 Shadow 结论后以 `active` 启用一次 Repair。真实模型运行前确认 API 配置可用。

- [ ] **Step 5: 填写人工复核模板并提交可复现资产**

模板包含每个案例的“可交付 / 应修复 / 不可交付”人工标记、Judge 结论、是否一致、修复是否改善、耗时和已知限制。只提交案例文件、Runner、模板与忽略规则，不提交 JSONL 原始结果。

Run: `pytest tests/test_resource_quality_gate.py tests/test_resource_gen_quality_flow.py tests/test_e2e_resource_workshop.py -v`

Expected: PASS。

```bash
git add .gitignore tests/fixtures/resource_workflow_cases.json scripts/run_resource_workflow_cases.py tests/test_resource_workflow_evidence_runner.py
git add ../docs/agent-engineering/resource-workflow-evidence-template.md
git commit -m "test: add resource workflow feedback loop"
```

## Final Verification

- [ ] 运行 `pytest tests/test_resource_quality_gate.py tests/test_resource_gen_quality_flow.py tests/test_resource_workflow_evidence_runner.py tests/test_e2e_resource_workshop.py -v`，确认全部通过。
- [ ] 运行 `python -m compileall -q app scripts tests`，确认新增 Python 文件可编译。
- [ ] 用固定案例完成基线、Shadow 和主动修复三轮记录；人工填写证据模板。
- [ ] 检查 `git status --short`，确认仅源代码、测试、案例、文档与忽略规则被提交，原始 JSONL/日志仍未跟踪。
- [ ] 更新 README 与简历材料时，仅引用人工复核和运行记录已确认的结果。
