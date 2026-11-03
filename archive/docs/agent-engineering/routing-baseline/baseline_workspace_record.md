# 候选测试基线记录（Stage 0.2 · 决策 1）

> 采集时间：2026-10-13
> 采集人：Coding Agent A
> 目的：为 Stage 0.2 及其后的基准评测**固化当前待测版本**，保证可复现。
> **本记录只采集，不改动任何文件**（未提交 / 未暂存 / 未还原 / 未覆盖）。

---

## 一、Git 版本

| 项 | 值 |
|---|---|
| 分支 | `for-work` |
| HEAD（完整） | `24dd24db67259bc5951f87a46023b0c6560b6eba` |
| HEAD（短） | `24dd24d` |
| 最近提交 | `fix(deps): make requirements.txt parseable on Chinese Windows`（Software-Fighters Dev，2026-10-10 09:14:04 +0800） |

> ⚠️ **HEAD 之上的工作区存在未提交改动**，因此「测试基线」≠ 仅由 commit 决定，必须 commit + 工作区快照共同锚定。

---

## 二、与路由行为相关的未提交改动（tracked）

| 文件 | 变更规模 | 是否影响路由行为 | 说明 |
|---|---|---|---|
| `ai-service/app/services/capability_gate.py` | +17 −0 | **一级路由：是** | 新增 `verb_topic_exercise` 规则（EXERCISE，不要求数量词） |
| `ai-service/app/centers/chat_task_dispatcher.py` | +36 −12 | **执行/收尾帧：是（非路由判定）** | `_finalize_event(streamed=)` 参数化；`_ON_TOKEN_MODES` 由 `{auto}` 扩为 `{auto, exercise}` |

**其余路由核心文件本工作区干净（无未提交改动）**：
`router_agent.py`、`chat_center.py`、`intent_extractor.py`、`schemas.py`、`routing_audit.py`、`internal_api/chat.py`、`app/api/models.py`。

diff 原文已存：`docs/agent-engineering/routing-baseline/routing_related_uncommitted.diff`（129 行）。

---

## 三、路由核心文件 SHA-256（工作区当前内容）

| SHA-256 | 文件 |
|---|---|
| `b1dca32ae8ef3567facc1ff58c2604e4e38bb687f8d38523ba6726fb41d1bf00` | `ai-service/app/services/capability_gate.py` |
| `91f4b555427c463bdea483fbd8363986e285fb2eb34fb1c975307224f9822cc2` | `ai-service/app/centers/router_agent.py` |
| `70f208b08e2c781047418594f5e4b9df1df2ad16f332a8f4e3bc3f8ce145fe8b` | `ai-service/app/centers/chat_center.py` |
| `d3e9292dff0d9f63a0335f07f306874380222a3def78f19ae7847212a02a545f` | `ai-service/app/services/intent_extractor.py` |
| `dc06ca5216cc7749b59950ea5bf6c0010e5030fcf9d58a75d2d6defc4d930ffa` | `ai-service/app/centers/schemas.py` |
| `ce478c5c4f552e5ef8413786c875aed18f9daa7b75ef46e16102abd7812cc42f` | `ai-service/app/centers/chat_task_dispatcher.py` |
| `76c7410eae4cecea5c89043df9a86572ddd710e49136763b305f8a39ed0d586b` | `ai-service/app/services/routing_audit.py` |
| `d63aeace8a5101fbb3376e5c1a7c0814160ad9edbcac3f5fe6a918c7f17465b9` | `ai-service/internal_api/chat.py` |
| `cc7cb3b1446fd6305204a92c14fb55c169eacdb50cdf31816fc18dba582d2638` | `ai-service/app/api/models.py` |

**在正式基准评测（Stage 0.3+）前必须重算上述哈希并与此表逐一比对；任何不一致即视为基线漂移，需重新采集。**

---

## 四、安全检查（确认不含敏感信息）

| 检查项 | 结果 |
|---|---|
| 未提交 diff 内容 | 仅路由/流式逻辑与中文注释，**无密钥、无个人数据、无内部 URL** |
| 采集的文件 | 仅 `.py` 源码 + `git diff` 文本，**不含 .env / 凭据 / 数据库导出** |
| 本目录新增文件 | 基线记录 + diff 文本，均可安全提交/共享 |

**结论：当前待测版本可安全固定。无阻碍。**

---

## 五、基线使用约定

1. **候选测试基线** = commit `24dd24d` **+** 本记录第三节的工作区哈希。
2. 工作区在 Stage 0.2 期间**保持只读**：不提交、不还原、不改路由源码。
3. 若工作区在评测前发生任何路由相关改动，本记录作废，须重新采集。
