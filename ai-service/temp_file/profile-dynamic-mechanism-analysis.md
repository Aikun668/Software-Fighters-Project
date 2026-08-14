# 学生画像动态变化机制 — 设计原理与真实 LLM 测试报告

> 生成日期：2026-06-17  
> 用途：供外部评审画像系统的算法设计是否合理

---

## 一、画像数据模型

### 1.1 六个维度

| 维度 | 类型 | 合并策略 |
|------|------|----------|
| `knowledge_base` | 整数 0-100 | EMA 加权平均 |
| `cognitive_style` | 枚举 (visual/auditory/kinesthetic/theoretical) | 替换 (stability-locked) |
| `learning_goal` | 字符串 | 替换 (stability-locked) |
| `weak_points` | 条目数组 | 增量追加 + 去重合并 |
| `learning_pace` | 字符串 | 替换 (stability-locked) |
| `interest_direction` | 条目数组 | 增量追加 + 去重合并 |

### 1.2 三类合并策略

**策略 A — NUMBER (knowledge_base 专用)**

```
merged = max(old_value, old_value × 0.7 + new_value × 0.3)
```

EMA 平滑 + 下限保护（只升不降）。

**策略 B — REPLACE + Stability Counter (cognitive_style / learning_goal / learning_pace)**

```
if current_value == new_value:
    确认，count=0, status=confirmed
elif previous_attempt == new_value:
    count += 1
    if count >= 2:   # STABILITY_N = 2
        替换 current_value = new_value, confirmed
else:
    重置 count=1, status=tentative（新候选出现）
```

设计意图：替换维度不能因为一次提取就修改。需要**连续 2 次提取出相同值**才确认替换。避免 LLM 一次误判就覆盖。

**策略 C — ARRAY + Entry Model (weak_points / interest_direction)**

每条条目是 `{text: string, confidence: 1-10, status: tentative|active|stale}` 的完整对象。

```
合并流程：
1. LLM 提取本轮新条目列表 new_items
2. 对每个 new_item：
   a. 用 bigram Jaccard (阈值 0.55) 与已有条目比对
   b. 相似 → 已有条目 confidence += 1, confidence>=2 时 status=active
   c. 不相似 → 创建新条目 confidence=1, status=tentative
3. 按 status(active>tentative>stale) 再按 confidence 降序排序
4. 超过 8 条时裁剪末尾
```

## 二、LangGraph 管线

```
用户消息 → extract(LLM) → merge(纯逻辑) → audit(LLM,触发条件) → response(LLM)
```

- **extract**: LLM 从对话中提取 6 维度 JSON（temperature=0.3）
- **merge**: 纯代码执行上述三类合并策略，产出更新后的 profile dict
- **audit**: 每处理 20 条新消息触发一次。LLM 审查所有已有条目是否仍成立（delete/update/keep）
- **response**: LLM 根据当前画像生成引导性追问（temperature=0.4）

## 三、真实 LLM 20 轮对话压力测试

### 3.1 测试设置

- LLM: DeepSeek-v4-pro（OpenAI 兼容 API）
- 对话: 20 轮渐进式学生自我介绍（从"完全不知道从哪里开始"到"补数学→学ML/DL→专攻CV"）
- 每轮独立 extract + merge，profile dict 跨轮累积传递

### 3.2 测试数据（节选）

```
轮 1: extract → knowledge_base=10, weak=["缺乏整体认知"], interest=["广泛兴趣未明确方向"]
轮 3: extract → interest=["想转行到AI方向，看好前景"], goal="想转行到AI方向"
轮 4: extract → interest=["对CV有明确兴趣，图像识别很酷"]  ← 新条目，未与轮3合并
轮 5: extract → weak=["数学基础较弱，线代概率论是短板"]     ← 新条目，未与轮1合并
轮 7: extract → goal="我希望能用半年时间入门，找AI相关工作" ← goal 改变！
轮 9: extract → cognitive_style="visual"
轮 11: extract → cognitive_style="kinesthetic"              ← style 翻牌
轮 13: extract → cognitive_style="visual"                  ← 又翻回去
轮 16: extract → weak=["数学基础比之前估计的更差"], kb=25  ← kb 想降
轮 20: extract → goal="补数学基础→系统学ML/DL→专攻CV方向" ← goal 又改变
```

### 3.3 终态快照

```
knowledge_base: 31          (10→13→21→25→28→30→31, 20轮涨21分)
cognitive_style: —          (visual↔kinesthetic 振荡, 从未达到稳定性阈值)
learning_goal: —            (4次不同值, 每次重置 stability counter)
weak_points: 8条 ○c=1       (没有一条晋升 active)
learning_pace: —            (2次不同值)
interest_direction: 5条 ○c=1 (没有一条晋升 active)
维度填充: 3/6                (20轮后仍不完整)
```

### 3.4 对照：Mock LLM（固定返回）同样 20 轮

```
knowledge_base: 30          (始终稳定)
cognitive_style: —          (mock 从不返回)
learning_goal: confirmed    (第2轮即确认)
weak_points: 1条 ●c=10      (第2轮晋升 active)
learning_pace: —            (mock 从不返回)
interest_direction: 1条 ●c=10 (第2轮晋升 active)
维度填充: 4/6                (第2轮即完备)
```

## 四、三个根因

### 根因 1：Entry Model 无法处理 LLM 措辞多样化

**设计假设**：同一概念会被 LLM 用相似措辞重复提取 → bigram 去重命中 → confidence 累积 → active 晋升。

**真实情况**：LLM 每次从不同角度描述，措辞差异大（"数学基础较弱" vs "看到数学公式焦虑" vs "矩阵运算完全遗忘"）。这些是**语义相关但 bigram 不相似的独立描述**，全部被当作新条目。

**结果**：20 轮后 8 条 weak_points 全是 tentative(c=1)，0 条 active。confidence 累积机制形同虚设。

### 根因 2：Stability Counter 死于精确字符串匹配

**设计假设**：同一维度被 LLM 连续两次提取出**完全相同的字符串**才算确认。

**真实情况**：
```
cognitive_style: visual → kinesthetic→ visual  (交替波动，count 永远归 1)
learning_goal:   "转行AI" → "半年入门找工作" → "图像分类实战" → "数学→ML→CV"
```

学生的真实表达每轮都在演化/细化，LLM 的提取也跟着变化。稳定性计数器的等于比较（`current_value == new_val`）在自然语言维度上永远不成立。

**结果**：3 个 REPLACE 维度（cognitive_style / learning_goal / learning_pace）在 20 轮后全部为空。

### 根因 3：knowledge_base 只升不降

```python
merged = max(old_value, old_value * 0.7 + new_value * 0.3)
```

`max()` 阻止分数下降。第 16 轮学生明确说"数学基础比之前估计的更差"，LLM 提取 kb=25。EMA 算出 28.5，`max(30, 28.5)=30`，锁定不降。

**结果**：画像不能随着学生自我纠偏而下修。

## 五、算法层面的设计评估

| 组件 | 设计质量 | 问题 |
|------|:---:|------|
| 6 维度定义 | ✅ 合理 | 覆盖面完整 |
| ARRAY Entry Model | ⚠️ 半失效 | bigram 去重太脆弱，需语义级相似度 |
| REPLACE Stability Counter | ❌ 失效 | 精确字符串匹配不适用于自然语言 |
| NUMBER EMA + max | ⚠️ 半失效 | EMA 合理，max() 阻止下修 |
| Audit 机制 | ✅ 设计正确 | 消息索引基准的触发条件合理 |
| 增量提取 (last_extracted_msg_index) | ✅ 合理 | 跳过已处理消息，避免重复 |
| 条目裁剪 (max 8 per dim) | ✅ 合理 | 按 status+confidence 优先级淘汰 |

## 六、改动代价评估

| 方案 | 改动范围 | LLM 调用增量 | 预期效果 |
|------|---------|:---:|------|
| A. 把 bigram 阈值从 0.55 降到 0.35 | 1 行 | 0 | 小修小补，误合并风险↑ |
| B. bigram → embedding 语义相似度 | ~50 行 + embedding 服务 | 0 | 去重准确率大幅提升 |
| C. Stability Counter 改为「值从未出现过就替换」 | ~30 行 | 0 | REPLACE 维度能被填上，但可能被一次误判覆盖 |
| D. C + 保留 stability 作为「连续 2 次不同于当前值才替换」 | ~50 行 | 0 | 平衡速度与稳定性 |
| E. knowledge_base 去掉 max() 或改为 min(old, EMA) 只做平滑 | 1 行 | 0 | kb 可以下修 |
| F. Entry confidence 不依赖 LLM 重复提取，改为语义聚类后按簇计频率 | ~80 行 + embedding | 0 | 根除 confidence 不累积问题 |

---

*全文由 Claude Code 根据 2026-06-17 真实 LLM 20 轮测试数据撰写。*
