# T4-C · 能力产物闭环 · 阶段报告

> 性质：**行为优化**（T4）。前置 T4-A/T4-B 完成。沿用 budget（每请求 ≤1 次语义 LLM、超时兜底）。

---

## 一、闭环结果

| 项 | 实现 | 验证 |
|---|---|---|
| 冷门意图识别（T4-B 遗留根因） | 语义腿 prompt 5 类 → 8 类（加 solve_problem/code_example/flashcard_gen） | 真模型实测：解具体题→solve_problem、代码→code_example(0.98)、闪卡→flashcard_gen(0.98)；p95 时延 2566→1285ms 反而更稳 |
| 数据依赖接线（T4-B 遗留） | `INTENT_DEPENDENCIES` 声明表 + 复合规划器填 `depends_on` 边 | exercise←diagnose/solve、learning_path←diagnose；纯顺序不填边 |
| 下游 center 消费 upstream | `exercise_center` 读上游 diagnose 的 `next_skill`/`mastery_vector` 定制 topic/difficulty | 3 条契约测试 |
| 三态结果语义（Gate ④） | `CenterResult.final_status`（success/degraded/error）+ Dispatcher 归一化透传 | 4 条契约测试 |
| mock 腿 params（code/flashcard） | 补 `suggested_types` 使 ResourceCenter type_direct 直通 Specialist | 5 条契约测试 |
| 产物变换指代（T4-B 遗留） | 从 referent marks 去掉「配套/整理成」等含新意图关键词的词，交语义腿判 | 真模型单句即可判对 4/5 |

---

## 二、关键发现

1. **T4-B「冷门意图识别弱」的真根因是 prompt 只 5 类**，不是模型差。扩到 8 类后
   solve/code/flashcard 全识别对，且时延更稳。
2. **资源域 Specialist 早已齐备**（code/flashcard/mindmap/project 都在），缺口只是
   mock 腿 params 无 `suggested_types` → 依赖 `_rule_route` 词根碰运气。补 params 即确定性直通。
3. **「产物变换」指代大多句子自带新意图关键词**，8 类语义腿单句即可判对；T4-B 把它当
   「复用上轮意图」是误判根源，已改为交语义腿。

---

## 三、未闭环（如实标注，非 T4-C 范围）

1. **画像边界（C111「对，我就是想转行」）**：gold=profile_building，8 类语义腿判 learning_path。
   画像涉及既有学习状态 + 授权（master plan T4-C 第 4 步），刻意未并入 prompt，需产品方单独定画像策略。
2. **diagnose/profile/knowledge_graph 仍靠关键词路由**：刻意不并入 prompt（既有学习状态 + 授权边界）。
3. **下游消费仅 exercise 域示范**：plan_center 消费 diagnose 上游定制计划尚未做（可后续按同法加）。
4. **「暂未完成能力的产品状态」**（Gate ②）：`final_status` 字段已就绪，但各 center 在产物空时
   置 `degraded` 的落点需逐个 center 补齐（本轮 exercise/resource 已具备 final_status 语义，其余待补）。

---

## 四、验证

- T4-C 新增契约测试：resource_params(5) + upstream_consume(3) + status(4) + 依赖边(3) + transform(1)。
- 全量核心回归：234 passed。
