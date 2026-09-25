# Agent Dev 后续开发计划

> 范围：ai-service（Python 多智能体系统）。不含前端、Java 后端。

---

## 一、当前状态基线

### 已完成

| 模块 | 完成度 | 说明 |
|------|--------|------|
| ProfileAgent + ProfileWorkflow | 95% | 6 维画像，EMA 动态权重，对话式构建 |
| ContentAgent | 100% | 课程讲解文档生成 |
| MindmapAgent | 100% | 思维导图生成 |
| ExerciseAgent | 100% | 练习题生成（选择/填空/简答） |
| ReadingAgent | 100% | 拓展阅读材料生成 |
| CodeAgent | 100% | 代码实操案例生成 |
| FlashCardAgent | 100% | 记忆闪卡生成 |
| ResourceGenWorkflow | 95% | 6 类资源并行生成编排 |
| LearningPathWorkflow | 90% | 个性化学习路径规划 |
| Director | 90% | 动态 Agent 路由（rule + LLM fallback） |
| TutorAgent | 85% | 多模态答疑（文字 + 图解 + 文件理解） |
| VisualizePipeline | 85% | 三阶段图表生成（分析→生成→审查） |
| Media Adapter | 60% | OpenAI 图片生成（mock 模式，未接真实 API） |
| EvaluationService | 60% | 基础评估 API 有，深层分析缺 |
| KnowledgeBase | 100% | ChromaDB + 嵌入检索 |
| SSE Streaming | 90% | 流式输出 + 心跳保活 + 多模态事件 |
| 内容安全 | 50% | content_guard 有基础，缺全面过滤 |
| 测试 | — | 468 测试通过 |

### 待提交

`feat-multimodal` 分支上有约 20 个文件未提交（包含 visualize pipeline、media adapter、mermaid parser、file parser/validator、bug fixes 等）。

---

## 二、比赛需求 → Agent Dev 差距分析

```
比赛要求                                  当前状态          差距
────────────────────────────────────────────────────────────────────
多模态视频/动画（4 次提及）                方案有了，代码 0    P0
学习效果评估（可选加分）                   骨架有，缺深度      P1
防幻觉/内容安全（强制非功能）              基础有，缺系统化    P1
智能辅导-短视频讲解                        方案有，代码 0     P2
个性化资源 ≥5 类                          6 类，已超额       ✅
多智能体协同                              10 Agent + 4 WF   ✅
流式输出 + Markdown 渲染                   后端就绪           前端的事
画像 ≥6 维动态更新                         EMA + 对话式      ✅
学习路径规划                               ✅                ✅
```

---

## 三、后续分阶段计划

### Phase 1：收束 feat-multimodal（1 天）

**目标：把散落的多模态代码收束到 main，清理技术债。**

- [ ] 提交 `feat-multimodal` 上所有待提交文件
- [ ] 合并到 `agent-dev` → 合并到 `main`
- [ ] 清理 `.claude-loop/` 和 `.sisyphus/` 临时目录（加入 .gitignore）
- [ ] 补 `app/agents/visualize/__init__.py`
- [ ] Media adapter 从 mock 切换到可配置（环境变量 `IMAGE_ADAPTER=openai`）
- [ ] 确认 468 测试全部通过

### Phase 2：多模态视频/动画生成（4-5 天）⭐ 最高优先级

**目标：满足比赛"多模态视频/动画"要求，这是 competitors 中最可能拉开差距的点。**

技术方案（已在多模态搬运分析中确定）：PPT+TTS+FFmpeg

```
LLM 生成幻灯片 JSON
  → python-pptx 渲染每页 → 导出 PNG
  → OpenAI TTS 生成每页旁白音频
  → FFmpeg 合成图片序列 + 音频 → MP4
```

**新增模块：**

- `app/services/video_generator.py` — 视频生成编排器
  - `generate_slides(topic, content) → list[SlideData]`
  - `render_slides_to_images(slides) → list[bytes]`
  - `generate_voiceover(texts) → list[bytes]`
  - `synthesize_video(images, audio) → bytes`

- `prompts/video_agent/slides.yaml` — LLM 提示词：生成幻灯片内容
  - 每页：标题 + 要点（≤5 条）+ 配图描述
  - 输出格式：JSON，每页一张幻灯片
  - 总页数 5-10 页

- `prompts/video_agent/script.yaml` — LLM 提示词：生成旁白脚本
  - 每页旁白 30-60 秒
  - 自然口语化

**依赖：**
- FFmpeg（系统安装）
- python-pptx（已有）
- OpenAI TTS API（已有 key，复用 media adapter 模式）

**可降级方案：** 如果 FFmpeg 不可用，降级为生成 PPT 文件 + 导出为图片序列（无音频合成，但仍可声称"动画"）。

### Phase 3：学习效果评估深化（3 天）

**目标：把评估从"能跑"提升到"产品级"。**

当前状态：`evaluation_service.py` 有基础 API（答题评分、学习报告生成）。缺什么：

- [ ] **多维评估模型**：不止对错，加时间维度（答题速度变化）、知识覆盖度、薄弱点趋势
- [ ] **自适应难度调整**：根据历史表现动态调整题目难度
- [ ] **错题归因分析**：LLM 分析错题根因（概念不清 vs 计算失误 vs 审题错误）
- [ ] **学习建议生成**：基于评估结果自动生成个性化学习建议
- [ ] **评估报告可视化数据**：输出结构化 JSON 供前端渲染图表

**新增/修改文件：**
- `app/services/evaluation_service.py` — 深化
- `app/agents/evaluation_agent.py` — 评估智能体（新增，LLM 驱动的深度分析）
- `prompts/evaluation_agent/` — 评估提示词

### Phase 4：防幻觉 + 内容安全（2 天）

**目标：满足"完善的防幻觉与内容安全过滤机制"非功能需求。**

- [ ] **事实性校验**：LLM 生成的课程内容对照知识库进行一致性检查
  - 对 ContentAgent 输出做 KB 回检
  - 标记低置信度内容
- [ ] **内容安全过滤**：敏感词检测 + 违规内容拦截
  - 扩展 `content_guard.py`
  - 接入讯飞内容审核 API（如有）
- [ ] **引用溯源**：答案中标注信息来源（来自知识库的哪个章节）
- [ ] **置信度评分**：每个 agent 输出附带置信度，低置信度内容标记为"仅供参考"

### Phase 5：智能辅导质量提升（3 天）

**目标：TutorAgent 从"能答"到"答得好"。**

- [ ] **解题步骤拆分**：复杂问题自动拆成步骤（借鉴 DeepTutor solve pipeline 的 Plan → Solve Step 模式）
- [ ] **追问引导**：回答后根据学生画像判断是否需要追问
- [ ] **类比库**：常见 AI 概念的类比集合，让解释更通俗
- [ ] **错误答案分析**：学生答错时不只给正确答案，分析"为什么这个错误很常见"
- [ ] **图片生成真实集成**：Media adapter 切到 OpenAI DALL-E，TutorAgent 回答中自动插入 AI 生成图

### Phase 6：性能 + 集成测试（2-3 天）

- [ ] **Agent 并行执行优化**：resource_gen 中 6 个 agent 的并行超时策略
- [ ] **资源缓存**：同一 topic 已生成的资源复用，避免重复 LLM 调用
- [ ] **E2E 测试**：至少覆盖 Tutor Chat 全流程、Resource Gen 全流程
- [ ] **API 文档**：internal_api.py 的接口文档

---

## 四、优先级总览

```
Phase 1: 收束 feat-multimodal           ████░░░░░░  1 天
Phase 2: 视频/动画生成 ⭐               ██████████  4-5 天    比赛最大差异化点
Phase 3: 学习效果评估深化               ██████░░░░  3 天      评分项 5
Phase 4: 防幻觉 + 内容安全               ████░░░░░░  2 天      非功能强制要求
Phase 5: 智能辅导质量提升               ██████░░░░  3 天      可选加分项
Phase 6: 性能 + 集成测试 + 文档          ██████░░░░  2-3 天    提交前
                                       ──────────
                                       约 15-17 天
```

预计剩余约 20 天，Phase 1-6 需要 ~15-17 天，留 3-5 天缓冲。

---

## 五、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 视频方案 | PPT+TTS+FFmpeg | 可控、可降级、不依赖 GPU |
| AI 视频 API | 不用 | Seedance/Kling 等 API 调用成本高、不稳定 |
| 评估模型 | LLM 驱动 + 规则辅助 | 灵活性 > 纯规则系统 |
| 防幻觉方案 | KB 回检 + 引用溯源 | 比纯 prompt 约束更可靠 |
| 代码新分支 | `feat-video-gen` | 视频功能独立于多模态输入 |

---

## 六、下一步行动

1. **立刻**：提交 feat-multimodal → 合 main（收束）
2. **然后**：从 feat-multimodal 最新 main 拉 `feat-video-gen` 分支
3. **开干**：Phase 2 视频生成（比赛最大差异化点）
