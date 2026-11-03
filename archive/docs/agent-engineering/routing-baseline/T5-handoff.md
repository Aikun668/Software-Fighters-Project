# T5 · SSE / Context / 跨域收口 · 阶段报告

> 性质：**结构改造**。红线：对外 SSE 契约（`sse_contract.json` sha256 `866a6c6d`）与用户可见行为不得变化。
> 前置：T4-A/B/C 完成。

---

## 一、四个 Gate 的结果

| Gate | 结论 | 证据 |
|---|---|---|
| ① 上下文分工明确 | ✅ 现状已满足，以契约 + 文档钉死 | `T5-context-map.md` + `test_t5_context_split_contract.py`(3) |
| ② SSE 契约统一 + Dispatcher 不混正文 | ✅ 红线守住 + 自动防线 + 正文合成迁出 | `chat_presentation.py` + `--verify` + `test_t5_presentation_extraction_contract.py`(3) + `test_t5_sse_contract_baseline.py`(1) |
| ③ 跨 Center 契约 | ✅ 已由既有合约锁定（本轮未新增） | `test_routing_ownership_contract.py` 等 104 条 |
| ④ 取消/超时/异常/重复 done | ✅ 已由既有合约锁定（本轮未新增） | `test_chat_center_stream_contract.py` 22 + `test_sse_contract.py` 17 |

---

## 二、本轮实际改动（3 个提交）

### 1. `fix(routing): keep final_status out of the SSE contract`（97eca2d）

**发现**：重生成 SSE 契约比对基线，sha256 `866a6c6d` → `18e943de`。
**根因**：T4-C 的 `_serialize_result` 把 `final_status` 泄漏进 done 载荷的 `results[]`（5 条链路各多一键）。
**修复**：`final_status` 是审计字段，保留在 `CenterResult` 上、从对外 SSE 载荷移除。
**验证**：重生成回到 `866a6c6d`。

### 2. `test(routing): add an automated SSE-contract baseline guard`（76cc5a0）

`probe_sse_contract.py` 原来只有生成模式 → 泄漏靠手动才发现。新增 `--verify`：重新生成 + 精确解析后 diff + 报差异路径 + 非零退出。
新增 `test_t5_sse_contract_baseline.py` 让每次回归自动守线。
**自证**：注入 `final_status` → `--verify` 报出 5 处精确路径、exit 1。

### 3. `refactor(centers): move presentation logic out of the dispatcher`（5dd01d2）

把 Dispatcher 混着的 5 个纯函数（正文合成 / SSE 帧拼装 / 摘要 / 建议）逐字迁到 `app/centers/chat_presentation.py`，Dispatcher 只调用不持有。
**零行为变化证明**：`--verify` exit 0，SSE 契约字节级不变。

---

## 三、Gate ① 的检查结论（`T5-context-map.md`）

- **路由层只依赖简要上下文**：`CapabilityGate.decide` / `RouterAgent._keyword_candidates` 只读 `message`(+mode)，`student_profile`/`context` 是兼容形参、函数体内零引用。
- 路由层对 context 的真实消费仅两处：审计（`messages` 轮数、`trace_id`、`conversation_id`）与 T4-B 指代消解（读上一轮 user 消息）。
- **无重复构建**（context 只在 `stream_chat` 构造一次）、**无相互覆盖**（路由只读、业务读全量、唯一写入是 T4-C 的 `upstream_results` 注入）。
- 契约钉死：路由层不得悄悄依赖画像/历史，若需依赖必须先改契约。

---

## 四、刻意不做（T5-Gate 允许的延期）

- **不拆分 context 数据类**：量级不足，会牵动 `stream_chat`/`route`/`plan_builder`/5 Center 签名，收益有限风险高。
- **不做 A 激进版**（把正文合成真迁到 `ChatCenter`）：B 已达成「Dispatcher 不再混正文合成」，A 属行为变更、收益边际。
- **双层图合并**（P3-B3b §0.3）：会让 `semantic_judge`/`audit` 开始执行 → 行为变更 + 需产品确认节点集，保持"只登记不合并"。
- **与 Java 落库边界核对**（T5 第 5 步）：涉及跨服务，不在纯 Python 仓库内可穷尽，留待 FINAL 阶段。

---

## 五、验证汇总

- SSE 契约：`--verify` 与基线一致（sha256 `866a6c6d`）。
- T5 新增契约测试：context(3) + presentation(3) + sse baseline(1) = 7 条。
- SSE / Dispatcher / T4 系列契约回归全绿。
