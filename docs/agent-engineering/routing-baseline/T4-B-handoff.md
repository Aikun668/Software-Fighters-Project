# T4-B · 复合任务与上下文依赖 · 阶段报告

> 性质：**行为优化**（T4）。前置 T4-A 已完成。沿用 budget：每请求 ≤1 次语义 LLM、超时兜底。
> 工作方式：先旁路对照、再以 `t4b_enabled` 开关启用（默认 off）。

---

## 一、四个缺口与结果

| 缺口 | 实现 | 对照结果（vs gold） |
|---|---|---|
| ① 复合诉求不被吞 + 顺序 | `detect_compound_order`（规则切分）+ `classify` 复合句判 UNCERTAIN + `_compound_plan_from_semantic`（语义多意图建多任务）+ `_reorder_by_compound`（顺序重排） | 15 条复合前2意图对齐 **3 → 9**；剩余 6 条是冷门意图（diagnose/solve_problem/code_example/knowledge_graph）识别弱，归 T4-C |
| ② 数据依赖 | `CenterTask.depends_on` + Dispatcher 注入 `context["upstream_results"]`（结构化，非长文本拼接） | 15 条里仅 3 条真依赖（诊断→计划/练习、解题→类似题）；无依赖任务不受影响 |
| ③ 多轮指代 | `detect_referent`（规则指代词）+ `_referent_plan`（复用上轮意图） | 20 条首意图对齐 **11 → 15**；剩余 5 条是「产物变换」（代码实现/调难度/配套练习/整理成图/转行），归 T4-C |
| ④ 部分失败语义 | Dispatcher 记录失败 sequence，阻断 `depends_on` 指向失败任务的后继（发 skip 语义 error），独立任务继续 | 契约测试锁定：上游失败跳过依赖者、独立任务照常 |

---

## 二、关键设计决策

1. **「吞诉求」的正解是语义腿多意图，不是子句级关键词路由**。真模型 `extract_multi` 对复合句已返回
   多意图（5/5 探针验证），而子句级关键词路由只 4/15。故让复合句走语义腿（`classify` 判 UNCERTAIN）、
   用多意图建多任务——**不加 LLM 调用**（UNCERTAIN 态本来就调那 1 次）。
2. **数据依赖只建模不硬编码消费**。`depends_on` + 结构化传递是 T4-B 交付；下游 center 具体怎么用
   `upstream_results` 是 T4-C 的业务闭环。
3. **指代消解只做「复用上轮意图」**（确定性规则，零 LLM）；「产物变换」类指代需要理解变换动作，归 T4-C。

---

## 三、开关与启用

- `t4b_enabled`（默认 False）控制三处行为变更：复合多任务、顺序重排、指代消解。
- 数据依赖注入与失败阻断**无条件生效**（它们是结构性增强，不改变「无依赖/无失败」时的行为；
  旁路指纹 `2624a51be09b9d5e` 不变——见下）。
- 生产启用需在 `internal_api._get_chat_center()` 显式传 `t4b_enabled=True`（同 T4-A 的装配层做法）。

---

## 四、验证

- 契约测试：T4-B 新增 4 文件（compound / reorder / compound_plan / referent / dependency）全绿。
- 核心路由回归：218 passed。
- 旁路指纹：`2624a51be09b9d5e`（T0 一致，`t4b_enabled=False` 时不改执行）。

---

## 五、未闭环（归 T4-C）

- 冷门意图识别弱（diagnose/solve_problem/code_example/knowledge_graph）——复合/指代里这几类仍偏差。
- 下游 center 真正消费 `upstream_results` 的业务逻辑。
- 「产物变换」类多轮指代（"调难度/配套练习/整理成图"）。
- 生产装配层 `t4b_enabled=True` 未拨（等 T4-C 一起灰度，或单独批准）。
