# T1 · 统一能力映射 · 阶段报告

> 基线：HEAD `882f458`（即 T0 基线 `24dd24d` + 两个路由文件 WIP 的提交）
> 性质：结构改造，不改任何映射值、执行顺序、关键词、SSE 行为。

## 一、统一了什么

6 张分散的映射表，现在只有一处真源：`ai-service/app/services/capability_map.py`（纯数据，无 import）。

| 表 | 原位置 | 现在 |
|---|---|---|
| INTENT_CENTER_MAP | intent_extractor.py | capability_map |
| CENTER_EXECUTION_ORDER（原 `_CENTER_EXECUTION_ORDER`） | intent_extractor.py | capability_map |
| MODE_TO_INTENT | router_agent.py（类属性） | capability_map，类属性引用同一对象 |
| KIND_TO_CENTER（原 `_KIND_TO_CENTER`） | chat_center.py | capability_map |
| MODE_TO_KIND | capability_gate.py | capability_map，gate 内派生为 `CapabilityKind` |
| ON_TOKEN_CENTERS（原 `_ON_TOKEN_MODES`） | chat_task_dispatcher.py | capability_map，类属性引用同一对象 |

契约测试 `tests/test_capability_map_contract.py` 做两件事：数值与 T0 冻结快照逐项一致；各消费方引用的是同一对象（防止以后复制一份）。

## 二、验收结果

| 检查 | 结果 |
|---|---|
| 路由快照（T0.3，140 条） | 指纹 `2624a51be09b9d5e`，与 T0 一致；0 异常、0 非确定 |
| SSE 契约（T0.4） | sha256 `866a6c6d…`，与 T0 一致 |
| 路由相关 pytest（10 个文件，含新契约测试） | 全部通过 |

## 三、尚未闭环（只记录，留给 T4-C）

- `flashcard_gen`、`code_example`：已注册并路由到 resource，但执行层没有对应分支。
- `adjust_plan`：`plan_center.py` 有分支，但不在意图注册表中，路由不可达。
- 未触及、不属于 T1 范围的表：INTENT_REGISTRY 关键词表、`_CAPABILITY_RULES`、`_MUTEX_GROUPS`、`_INTENT_PRIORITY`。

## 四、已知影响

- `t0_2_extract_mappings.py` 仍按旧位置导入，现在无法直接运行。`legacy_mappings.json` 是冻结快照，未改动。如需重新抽取，应在基线提交 `882f458` 的检出副本上运行。

## 五、状态与是否可进入 T2

- T1 的改动**尚未提交**，留在工作区，等待你确认后再提交。
- 满足 T1-Gate 的四项要求，**建议可以进入 T2**。T2 需要你单独授权。
