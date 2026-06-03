# Claude + DeepSeek 二人转协作规范

## 概述

这是 Claude（Planner）和 DeepSeek（Builder）共同遵守的协作宪法，确保文档闭环流转。

---

## 目录结构

```
.claude-loop/
├── active/                          # 当前进行中的轮次
│   ├── 01-claude-plan.md           # Claude 下达的计划
│   └── 02-deepseek-code.md         # DeepSeek 执行报告
├── history/                         # 已完成的历史轮次归档
│   └── round-YYYYMMDD-HHMMSS/      # 每轮迭代的完整记录
├── claude-rules.md                  # Claude 的铁则
├── deepseek-rules.md                # DeepSeek 的铁则
└── README.md                        # 本规范声明
```

---

## 闭环流转机制

### 流程图

```
Claude → 01-claude-plan.md
    ↓
DeepSeek ← 01-claude-plan.md
    ↓
02-deepseek-code.md
    ↓
Claude ← 02-deepseek-code.md（验收 + 下一轮计划）
    ↓
(循环) → Claude → ...
```

### 步骤说明

每个角色开工前先读自己的 `*-rules.md` 铁则文件，然后再进入正式流程。

#### 1. Claude（Planner）

**启动流程：**
```bash
# 读取上一轮 DeepSeek 的报告（如果有）
cat .claude-loop/active/02-deepseek-code.md

# 归档上一轮
ROUND_ID=$(date +%Y%m%d-%H%M%S)
mkdir -p .claude-loop/history/round-$ROUND_ID
mv .claude-loop/active/* .claude-loop/history/round-$ROUND_ID/

# 写新计划
# 编辑 .claude-loop/active/01-claude-plan.md
```

**职责：**
- 先读 `claude-rules.md`
- 再读 `active/02-deepseek-code.md`（上一轮结论）
- 归档上一轮的 2 个文件到 `history/round-XXX/`
- 清空 `active/`，写入新计划 `01-claude-plan.md`

#### 2. DeepSeek（Builder）

**启动流程：**
```bash
# 读取 Claude 的计划
cat .claude-loop/active/01-claude-plan.md

# 执行代码修改
# ...

# 写报告
# 编辑 .claude-loop/active/02-deepseek-code.md
```

**职责：**
- 先读 `deepseek-rules.md`
- 再读 `active/01-claude-plan.md`
- 执行完成后写入 `active/02-deepseek-code.md`

#### 3. 循环

等待 DeepSeek 完成后，Claude 开启下一轮。

---

## 规则

* **禁止**在 `.claude-loop/` 根目录直接创建 .md 文件
* **禁止**在 `active/` 目录存放超过 1 个周期的文件
* 每个轮次完成后必须归档到 `history/round-XXX/`
* 命名规范：`01-xxx.md`, `02-xxx.md`

---

## 任务 ID 命名规范

格式：`TASK-DAYXX-NNN`

示例：
- `TASK-DAY01-001`：Day 1 的第 1 个任务
- `TASK-DAY01-002`：Day 1 的第 2 个任务
- `TASK-DAY02-001`：Day 2 的第 1 个任务

---

## 文件模板

### 01-claude-plan.md 模板

```markdown
# Claude 计划 | Round DAYXX-NNN | 日期

## 任务 ID
TASK-DAYXX-NNN

## 任务类型
[feature / bugfix / refactor / config / infra]

## 目标
（一句话）

## 背景
（可选）为什么要做

## 验收标准
- [ ] 条件 1
- [ ] 条件 2
- [ ] 条件 3

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| path/to/file | 新建/修改/删除 | 说明 |

## 约束条件
- 不能修改 XXX 文件
- 不能破坏 XXX 接口

## 验证方式
```bash
# 可执行的命令
```

## 给 DeepSeek 的注意事项
- 注意事项 1
- 注意事项 2

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAYXX-NNN
```

### 02-deepseek-code.md 模板

```markdown
# DeepSeek 报告 | Round DAYXX-NNN | 日期

## 任务 ID
TASK-DAYXX-NNN

## 执行结果
[✅ 成功 / ❌ 失败 / ⚠️ 部分完成]

## 修改文件清单
| 文件 | 操作 | 说明 |
|------|------|------|
| path/to/file | 修改 | 具体改了什么 |

## 验收标准完成情况
- [x] 条件 1 → 完成（说明）
- [ ] 条件 2 → 未完成（原因）
- [x] 条件 3 → 完成

## 测试结果
```bash
$ 运行的命令
输出结果
```

## 已知问题
- 问题 1
- 问题 2

---
产出文件：.claude-loop/active/02-deepseek-code.md | Round DAYXX-NNN
```

---

## 反馈自愈

用户指正某个角色时（说错、偏好、新红线），该角色自行更新对应的 `*-rules.md`，在本轮报告末尾注明"已更新 [role]-rules.md"。

---

## 当前状态

等待 Claude 写第一个计划（TASK-DAY01-001）

---

## 快速启动命令

### Claude 归档并开始新轮次
```bash
cd .claude-loop
ROUND_ID=$(date +%Y%m%d-%H%M%S)
mkdir -p history/round-$ROUND_ID
mv active/* history/round-$ROUND_ID/ 2>/dev/null || true
echo "归档完成：history/round-$ROUND_ID"
```

### DeepSeek 读取计划
```bash
cat .claude-loop/active/01-claude-plan.md
```

### 查看历史
```bash
ls -lt .claude-loop/history/
```
