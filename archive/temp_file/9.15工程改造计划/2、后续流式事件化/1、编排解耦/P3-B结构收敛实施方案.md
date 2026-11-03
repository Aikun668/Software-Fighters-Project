# P3-B 实施方案（结构变化：死代码清理 + 重命名 + 归位）

> 依据：P3-A 验收记录 `验收记录/P3-A-路由与命名约定-2026-09-24.md` §七 的 9 项待办。
> 前置：P3-A 已把三类决策与命名**立约并钉成契约测试**（19 例）。
> 本文件**未跟踪**。
> 定性：P3-B **不是**"零行为变化"轮（删代码/改名是真实结构变化），但**响应字节应仍零变化**。

---

## 零、逐项诊断（爆炸半径实测）

| # | 项 | 位置 | 引用者（实测） | 测试影响 | 风险 |
|---|---|---|---|---|---|
| **B1** | 死代码：`RouterAgent._use_llm` | `router_agent.py:54` | **0**（赋值后无读取） | 0 | 低 |
| | 死代码：`RouterAgent._intents_to_tasks` | `router_agent.py:211-231` | **0**（含测试） | 0 | 低 |
| | 死代码：`self.intent_extractor` 赋值 | `router_agent.py:53` | **0**（仅赋值处出现） | 0（**构造参数必须保留**） | 低 |
| | 随之：`import os` 变成未使用 | `router_agent.py:2` | 仅 `_use_llm` 用它 | 0 | 低 |
| **B2** | 图节点改名：`"director"` / `_director_node` / `_route_after_director` | `profile_workflow.py:55,61,64,87,124` | `tests/test_workflows.py:80,85,90`（3 行） | 1 文件 3 行 | 低 |
| **B3** | `ResourceWhiteboard` 归位 | `app/workflows/resource_whiteboard.py` | 仅 `tests/test_resource_whiteboard.py:5`；**无生产引用** | 1 行 import | 低 |
| **B4** | `Director` → 语义化名 | `app/orchestration/director.py:99` | `orchestration/__init__.py:3,5`、`resource_gen.py:30,130`、`test_orchestration.py:7,371,575`、`test_e2e_resource_workshop.py:238,575`、`stress_test_20.py:7`、`bombardment_test.py:12` | 5 文件 | 中 |
| | 附加：`ResourceGenWorkflow.director` 实例属性 | `resource_gen.py:130` | `test_orchestration.py:571`（`wf.director._model_profile`） | +1 行 | 中 |
| **B5** | `DomainRouter` → 语义化名 | `app/services/domain_router.py:22,75` | `tutor_agent.py:8,251`；`test_tutor_leak_regression.py:97,249`（**monkeypatch 字符串路径**）、`test_tutor_agent.py:230` | 3 文件 | 中 |
| **B6** | `RouterAgent` / `ResultAgent` 改名 | `app/centers/*.py` | `chat_center.py` + **10 个测试文件**（import/构造/stub 命名）+ 字面串断言 | 10+ 文件 | **高** |
| **B7** | 状态范围收敛（双层 LangGraph / 穿透私有节点 / 实例级 `_on_token`） | `profile_workflow.py`、`learning_path.py:70,88`、`base_agent.py:128-139` | 多个 | 行为变更 | **高** |
| **B8** | `ResultAgent` 跨域总调度收敛（**GUIDE P2 遗留**） | `result_agent.py:189-200` | 多个 | 行为变更 | **高** |

### 0.1 两个关键确认

1. **改名不影响 SSE 字节**：全仓搜 `"director"` 字面量，只命中 `profile_workflow.py` 的节点注册、
   `resource_gen.py` 的属性名与 `auto_center.py` 的注释 —— **没有任何 SSE 事件把 `director` 当 stage/字段发给前端**。
   （`test_exercise_center_api_contract.py:628` 的 `progress_event("director", ...)` 是练习域独立用例，与资源/画像 `Director` 无关。）
2. **`RouterAgent(intent_extractor=...)` 构造参数被 10 个测试文件使用** → 参数名属测试契约，**不能删**；
   死的是"存下来却没人读"那一半。

---

## 一、建议切分（三轮）

| 轮次 | 内容 | 性质 | 建议 |
|---|---|---|---|
| **P3-B1** | B1 + B2 + B3 | 纯结构（删死代码 / 改名 / 归位），**响应字节零变化** | **本轮做** |
| **P3-B2** | B4 + B5（+ B6 视情况） | 重命名，逐个 commit + 先补老名负向断言 | ✅ 已完成（B4+B5；B6 建议不做）｜`验收记录/P3-B2-重命名-2026-09-24.md` |
| **P3-B3** | B7 + B8 | **行为变更**，需独立验收口径 | 🟡 **B3a 已完成**（状态范围 + 节点协议 + 分发职责，零行为变化）｜B3b（合并双层图 / 迁移 SSE 职责）**待产品确认**｜`验收记录/P3-B3a-状态范围收敛-2026-09-24.md` |

> 切分理由：B1–B3 的"改动 ↔ 影响"完全可枚举（合计仅 1 个测试文件 3 行 + 1 行 import），
> 且能用现有字节存证证明"响应零变化"；B4/B5/B6 是"名字级契约"改动，需要新的验收手法（老名负向断言）；
> B7/B8 会改行为，不该和结构轮混在一起。

---

## 二、需要你拍板的决策点

| # | 决策 | 推荐 | 备选与代价 |
|---|---|---|---|
| **D1** | 本轮范围 | **P3-B1（B1+B2+B3）** | (a) B1+B2（不含资源白板归位）；(b) B1 只删死代码；(c) 一路做到 B4/B5（把 B2 经验直接用上，但测试面扩大到 8 个文件） |
| **D2** | `Director` 改名时是否连**实例属性** `ResourceGenWorkflow.director` 一起改 | 本轮不做（属 B4） | — |
| **D3** | `ResourceWhiteboard` 处置 | **移到 `app/orchestration/`**（它也 bridge 到 `orchestration/agent_turn_summary.py`） | 备选：删除（连带删 `tests/test_resource_whiteboard.py` 的 10 例）；或保持原位只改 docstring（P3-A 已做） |
| **D4** | `DeepSolveWorkflow` 处置 | **本轮只登记**（接线属新行为，删除需产品确认） | — |
| **D5** | 是否顺带清理 `RouterAgent` 的 `intent_extractor` 参数（改成显式弃用注释） | **只加注释，不删参数** | 删参数会断 10 个测试文件 |

---

## 三、P3-B1 技术方案

### 3.1 B1 死代码清理（`app/centers/router_agent.py`）

```diff
-import logging
-import os
+import logging

     def __init__(self, intent_extractor: IntentExtractor | None = None):
-        self.intent_extractor = intent_extractor or IntentExtractor()
-        self._use_llm = os.getenv("INTENT_USE_LLM", "").strip().lower() in ("1", "true", "yes")
+        # `intent_extractor` 参数保留以兼容既有测试签名（10 个测试文件传参）；
+        # 当前实现只做关键词路由，不读取该实例 —— 属 P3-B 登记项，暂不删参数。
+        del intent_extractor

-    def _intents_to_tasks(...):   # 整段删除（零引用）
-        ...
```

- `IntentExtractor` 的 import **必须保留**：`__init__` 的类型注解 `intent_extractor: IntentExtractor | None` 在 def 时求值。
- `_mock_extract_params` / `INTENT_CENTER_MAP` / `_CENTER_EXECUTION_ORDER` 等 **仍被 `_keyword_route` / `_manual_mode_plan` 使用**，不动。
- 删除后 `import os` 无引用 → 一并删除。

### 3.2 B2 图节点改名（`app/workflows/profile_workflow.py`）

| 旧 | 新 |
|---|---|
| 节点字符串 `"director"` | `"completeness_check"` |
| `_director_node` | `_completeness_check_node` |
| `_route_after_director` | `_route_after_completeness_check` |

同步：`tests/test_workflows.py:80,85,90` 的 3 处调用；日志文案 `Profile director check:` → `Profile completeness check:`。

### 3.3 B3 `ResourceWhiteboard` 归位

```text
app/workflows/resource_whiteboard.py  →  app/orchestration/resource_whiteboard.py
```
同步：`tests/test_resource_whiteboard.py:5` 的 import。
（`resource_whiteboard.py` 内部 `from app.orchestration.agent_turn_summary import AgentTurnSummary` 是**函数内惰性 import**，移动后仍成立。）

---

## 四、Task 切分（P3-B1）

| Task | 主题 | 内容 | 期望 |
|---|---|---|---|
| 1 | `test(routing): lock P3-B1 structure before cleanup` | 在 `test_routing_ownership_contract.py` 加 Part D：断言 `_use_llm` / `_intents_to_tasks` / `self.intent_extractor` **不存在**；`os` 未导入；节点名/函数名已改；白板模块位置已变 | **RED** |
| 2 | `refactor(routing): drop dead code in RouterAgent` | B1 | GREEN（部分） |
| 3 | `refactor(profile): rename director node to completeness_check` | B2 + 改 `test_workflows.py` 3 行 | GREEN |
| 4 | `refactor(orchestration): move ResourceWhiteboard out of workflows` | B3 + 改测试 import 1 行 | GREEN |
| 5 | 验收记录 + 存证 | 字节存证 + 回归 + `验收记录/P3-B1-结构收敛-<date>.md` | docs |

> 本轮**不提交**（等用户指令）。

---

## 五、验收标准（P3-B1）—— 已完成

- [x] 结构：`RouterAgent` 不含 `_use_llm` / `_intents_to_tasks` / `self.intent_extractor`；`os` 未导入（`RO-D01/D02`）
- [x] 结构：`profile_workflow` 的节点名与两个函数名已改；`test_workflows` 同步（`RO-D03`）
- [x] 结构：`app/workflows/` 下不再有 `resource_whiteboard.py`；新位置可 import（`RO-D04`）
- [x] **响应字节零变化**：SSE 19 / 图谱 27 / 计划 9 = 55 条 per-case sha256 逐条一致
- [x] 回归：305 passed / 2 skipped，无新增失败
- [x] P3-A 的 19 例契约测试仍全绿（`RO-A06` 等未被破坏）—— 仅 `NAMING_MODULES` 中白板路径随迁移更新（方案 D3 明示）
- [x] Java / 前端 / `internal_api/` 零改动
- [x] 小 review：零残留引用、零 lint；发现并修复 1 处文档不一致

> 验收记录：`验收记录/P3-B1-结构收敛-2026-09-24.md`（含 review 明细 §三）

---

## 六、风险

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | 删 `self.intent_extractor` 后某个 verify 脚本读它 | 低 | 全仓已确认仅赋值处出现；Task 1 加"不存在"断言 |
| 2 | 节点改名影响图执行 | 低 | 三处引用同文件内；`test_workflows.py` 3 例即验证 |
| 3 | 误把"结构变化轮"当"零行为变化轮"验收 | 中 | 验收口径写清：**响应字节**零变化，代码结构有变化 |
| 4 | 白板移动后 `__pycache__` 残留旧路径 | 低 | 移动后清理对应 `.pyc` |
| 5 | 删 `import os` 后 `os` 在别处被隐式使用 | 低 | 全仓 grep 已确认仅 1 处使用 |
