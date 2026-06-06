# Claude 计划 | Round DAY05-002 | 2026-05-30

## 任务 ID
TASK-DAY05-002

## 任务类型
feature

## 目标
新建评估服务，实现练习题自动批改（选择题本地比对 + 简答题 LLM 评分）和学习报告生成，同时接入 profile 增量更新和 API 端点。

## 背景
ExerciseAgent 能出题，但出完后无人批改。学生做了题拿不到反馈，学习效果无法量化，画像也无法随练习结果动态更新。对标 OpenMAIC 的 grading.ts（本地比对）+ eval/judge.ts（LLM 评分量规）。

## 验收标准
- [ ] `grade_choice(user_answer, correct_answer)` 本地比对，大小写不敏感、去空白，返回 `{correct, score: 0|1, correct_answer}`
- [ ] `grade_short_answer(user_answer, reference_answer, rubric)` 调用 LLM 评分，返回 `{score: 0-100, feedback, key_points_matched, key_points_missed}`，对空答案/LM 失败有降级处理
- [ ] `evaluate_session(answers)` 逐题批改 → 汇总总分 → 识别弱项模块（模块得分 < 60%）
- [ ] `generate_report(eval_results, student_profile)` 输出 `{overall_score, dimension_scores, weak_areas, suggestions}`，suggestions 按分数段分档（<60 / 60-80 / >80）
- [ ] `ProfileService.incremental_update(user_id, report)` 用报告结果更新画像：weak_points 合并去重，knowledge_base 加权更新（旧 70% + 新 30%）
- [ ] `POST /internal/exercise/grade` 端点，支持 choice 和 short_answer 两种题型
- [ ] `POST /internal/evaluation/report` 端点，接收评估结果 + user_id，生成报告并触发画像增量更新
- [ ] `python -m pytest tests/test_evaluation.py -v` 全部通过
- [ ] `python -m pytest tests/ -v` 现有测试不回归

## 关键文件
| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `app/services/evaluation_service.py` | 新建 | grade_choice + grade_short_answer + evaluate_session |
| `app/services/evaluation_report.py` | 新建 | generate_report |
| `app/services/profile_service.py` | 修改 | 新增 incremental_update 方法 |
| `internal_api.py` | 修改 | 新增 2 个端点 |
| `tests/test_evaluation.py` | 新建 | 覆盖三种评分函数 + 报告生成 + 画像更新 |

## 约束条件
- 不能修改 `app/agents/exercise_agent.py`——只做批改，不改出题逻辑
- 不能修改 `app/models/` 下任何模型文件
- 不能修改 `app/services/knowledge_base.py`
- LLM 评分失败时不能抛异常，必须降级返回 `score: 0`
- 选择题的 `choices` 参数只透传不参与匹配逻辑

## 验证方式
```bash
cd ai-service
python -m pytest tests/test_evaluation.py -v
python -m pytest tests/ -v
```

## 给 DeepSeek 的注意事项
- LLM 调用用 `llm.chat([{"role": "user", "content": prompt}])`，不是 `llm.generate()`
- 给 LLM 的评分 prompt 里要求返回纯 JSON，但 LLM 可能在外面包文字——需要从响应中提取第一个 `{...}` 区间再 json.loads
- 简答题空答案直接返回 score=0，不要浪费 LLM 调用
- `evaluate_session` 里，选择题 score 是 0 或 1，简答题 score 是 0-100，计算总分时注意归一化
- 弱项模块阈值：模块总分/满分 < 0.6 视为弱项
- `incremental_update` 里 knowledge_base 的加权公式里，如果旧值为 None 视为 0
- 画像的 weak_points 是 list[str]，合并时去重保留原有格式

---
产出文件：.claude-loop/active/01-claude-plan.md | Round DAY05-002
