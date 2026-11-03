# T5 · 统一上下文分工（路由简要 vs 业务专业）

> 目的：T5-Gate ①「路由上下文、业务上下文的获取和更新职责明确，没有明显重复构建或相互覆盖」。
> 本文是**现状登记 + 契约钉死**，不改任何行为。

---

## 一、上下文从哪来

唯一入口：`ChatCenter.stream_chat`（`app/centers/chat_center.py:643-650`）构造：

```python
context = {
    "messages": history + [{"role": "user", "content": message}],
    "style": style,
    "images": images,
    "user_id": user_id,
    "conversation_id": conversation_id,
}
```

再由 `route(message, mode, student_profile, context)` 消费；`student_profile` 与 `context` 是**并列参数**（不塞进 context）。

---

## 二、谁消费什么（现状，逐行证据）

### 路由层（只依赖简要上下文）

| 消费点 | 位置 | 用途 |
|---|---|---|
| `message` + `mode` | `CapabilityGate.decide` | 一级能力守门（**不读 profile/context**） |
| `message` | `RouterAgent._keyword_candidates` | 二级关键词意图（**不读 profile/context**） |
| `context["messages"]` | `chat_center.py:138` | 审计：历史轮数 |
| `context["trace_id"] / ["conversation_id"]` | `chat_center.py:148-149` | 审计元数据 |
| `context["messages"]` | `chat_center.py:354`（T4-B `_referent_plan`） | 跨轮指代消解（读上一轮 user 消息） |

> **契约**：`test_t5_context_split_contract.py` 钉死「gate / router 关键词路径不消费 profile/context」。
> 将来若要让路由依赖画像或历史，必须先改该契约（即显式决策，不得悄悄依赖）。

### 业务层（专业上下文，随 task 下发）

- `plan_builder._task_context`（`plan_builder.py:86`）：`{**context, "student_profile": student_profile}` → 每个 `CenterTask.context`。
- 各 Center / Agent 从中取 `messages` / `student_profile` / `images` / `style` / `user_id` / `conversation_id`。

### 产物层

- `course_id`：`chat_center.py:737` 推荐抽取用；来自 `plan.tasks[0].context`。

---

## 三、「重复构建 / 相互覆盖」检查结论

- **无重复构建**：context 只在 `stream_chat` 构造一次，向下一路透传（`{**context, ...}` 只做增量叠加，不重建）。
- **无相互覆盖**：路由层只**读** `messages` 的两个键，不写 context；业务层读全量，不回写。唯一写入是 `depends_on` 注入（T4-C，写 `task.context["upstream_results"]`，不影响路由键）。
- **结论**：Gate ①「职责明确、无重复构建或相互覆盖」**现状已满足**，本轮以契约 + 本文钉死。

---

## 四、刻意不做（T5 本阶段边界）

- **不拆分 context 类型**（不为"路由上下文"另建数据类）：当前量级下拆分会牵动 `stream_chat` / `route` / `plan_builder` / 5 Center 的签名，收益有限、风险高（T5-Gate 允许「风险大收益有限可标记延期」）。
- **不新增裁剪逻辑**：`messages` 未做长度裁剪；若将来需要，应在 `stream_chat` 构造处统一加，而非各 Consumer 各自裁。
