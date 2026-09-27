"""Pydantic request models — Architecture #2: Java 在请求体中传入所有数据"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ── Profile ────────────────────────────────────────────────────

class ProfileChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="对话消息数组 [{role, content}]")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


class ProfileWorkflowStatusRequest(BaseModel):
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


# ── Resources ──────────────────────────────────────────────────

class ResourceGenRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000, description="资源主题")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    resource_type: str | None = Field(
        default=None,
        description="资源类型: document|interactive_diagram|code|project|mindmap|flashcard。"
                    "前端按钮可显式传入；不传则由 Director 从 topic 自动推断。",
    )


class ExportPptxRequest(BaseModel):
    content_blocks: list = Field(default_factory=list, description="PPT 内容块")
    title: str = Field(default="AI学习资源", description="PPT 标题")


class ExportDocxRequest(BaseModel):
    content_blocks: list = Field(default_factory=list, description="DOCX 内容块")
    title: str = Field(default="AI学习资源", description="DOCX 标题")
    sub_type: str = Field(default="overview", description="文档子类型: overview|guide")


class ExportPdfRequest(BaseModel):
    content_blocks: list = Field(default_factory=list, description="PDF 内容块")
    title: str = Field(default="AI学习资源", description="PDF 标题")


# ── Tutor ──────────────────────────────────────────────────────

class TutorChatRequest(BaseModel):
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    messages: list[dict] = Field(..., min_length=1, description="完整对话消息数组（Java 传入）")


# ── Exercise ───────────────────────────────────────────────────

class ExerciseGenRequest(BaseModel):
    topic: str = Field(default="", description="题目主题（与 knowledge_node_id 二选一，knowledge_node_id 优先）")
    knowledge_node_id: Optional[str] = Field(default=None, description="知识图谱节点 ID（优先，传入后自动推断 topic）")
    strategy: Optional[Literal["weakness", "review", "new"]] = Field(
        default=None, description="出题策略：weakness=薄弱子概念, review=错题同类, new=新题"
    )
    count: int = Field(default=3, ge=1, le=20, description="题目数量")
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium", description="难度")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    user_id: int = Field(default=1, description="用户 ID")


class GradeRequest(BaseModel):
    type: Literal["choice", "short_answer", "code"] = Field(..., description="题目类型")
    user_answer: Optional[str] = Field(default=None, description="用户答案")
    correct_answer: Optional[str] = Field(default=None, description="正确答案（选择题）")
    choices: list = Field(default_factory=list, description="选项列表")
    multi: bool = Field(default=False, description="是否多选题")
    points: int = Field(default=1, ge=0, description="分值")
    reference_answer: str = Field(default="", description="参考答案（简答题）")
    rubric: str = Field(default="", description="评分标准（简答题）")


# ── Solve ──────────────────────────────────────────────────────

class SolveRequest(BaseModel):
    question: str = Field(..., min_length=1, description="需要解答的问题")
    context: str = Field(default="", description="知识库上下文（可选）")
    user_id: int = Field(default=1, description="用户 ID")


class ErrorAnalysisRequest(BaseModel):
    errors: list[dict] = Field(..., min_length=1, description="错题列表 [{question, user_answer, correct_answer}]")
    level: int = Field(default=1, ge=1, le=5, description="学生水平 1-5")


# ── Evaluation ─────────────────────────────────────────────────

class EvaluationReportRequest(BaseModel):
    evaluation_results: dict = Field(..., description="评估结果")


# ── Unified Chat ───────────────────────────────────────────────

class UnifiedChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户自然语言输入")
    user_id: int = Field(default=1, description="用户 ID")
    mode: Literal["auto", "plan", "resource", "exercise", "visualization"] = Field(
        default="auto", description="对话模式: auto=自动路由, plan=学习计划, resource=资源生成, exercise=练习, visualization=可视化"
    )
    conversation_id: Optional[int] = Field(default=None, description="会话 ID（Java 传入，仅供参考）")
    style: Optional[Literal["standard", "socratic"]] = Field(default="standard", description="tutor 子风格")
    messages: list[dict] = Field(default_factory=list, description="历史消息列表（Java 传入）")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    images: list[str] = Field(default_factory=list, description="用户上传的图片 URL 列表（Java 传入，可选）")


# ── Inquiry ──────────────────────────────────────────────────────

class InquiryResolveRequest(BaseModel):
    original_message: str = Field(..., min_length=1, description="原始用户消息")
    answers: list[str] = Field(..., min_length=1, description="用户对追问的回答列表")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    questions: list[dict] = Field(default_factory=list, description="追问列表")
    suggested_types: list[str] = Field(default_factory=list, description="推荐的资源类型")
    clarified_topic: str = Field(default="", description="澄清后的主题")


# ── Knowledge Graph ──────────────────────────────────────────────

class KnowledgeGraphRequest(BaseModel):
    masteries: dict[str, float] = Field(default_factory=dict, description="用户各节点掌握度 {node_id: mastery}")


class KnowledgeGraphNodeRequest(BaseModel):
    masteries: dict[str, float] = Field(default_factory=dict, description="用户各节点掌握度")
    total_exercises: int = Field(default=0, description="该节点练习总数")
    last_practiced: Optional[str] = Field(default=None, description="上次练习时间 ISO 字符串")


class GraphExtractRequest(BaseModel):
    course_id: str = Field(..., min_length=1, description="课程 ID")
    user_message: str = Field(..., min_length=1, description="用户消息")
    assistant_reply: str = Field(..., min_length=1, description="助手回复")
    existing_node_ids: list[str] = Field(default_factory=list, description="已存在的节点 ID 列表")


class GraphUpdateRequest(BaseModel):
    action: Literal["add_node", "add_edge"] = Field(..., description="更新动作类型")
    data: dict = Field(..., description="动作负载数据")


class GraphNodesRequest(BaseModel):
    course_id: str = Field(..., min_length=1, description="课程 ID")
    updates: list[GraphUpdateRequest] = Field(default_factory=list, description="节点/边更新列表")


class MasteryEvent(BaseModel):
    node_id: str = Field(..., min_length=1, description="知识图谱节点 ID")
    event_type: Literal[
        "resource_viewed", "exercise_done", "exercise_failed",
        "tutor_question_asked", "manual_correction",
    ] = Field(..., description="学习事件类型（P1 §4.2：现有 4 值 + 人工纠正）")
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="分数 (exercise_done 时需传)")


class MasteryUpdateRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度 {node_id: mastery}")
    events: list[MasteryEvent] = Field(..., min_length=1, description="学习事件列表")


class GraphReloadRequest(BaseModel):
    """管理员触发热更新骨架。"""
    pass


class GraphProgressRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="各节点掌握度")


class GraphPrerequisiteRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    node_id: str = Field(..., min_length=1, description="待检查的节点 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="各节点掌握度")
    threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="前置条件通过阈值")


class NodeDeleteRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")


class NodeUpdateRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    updates: dict = Field(..., description="要更新的字段 {name?, description?, difficulty?, category?, type?}")


class GraphSuggestEdgesRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")


class GraphMermaidRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="各节点掌握度")


class GraphLayeredRequest(BaseModel):
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="各节点掌握度")


# ── Learning Evidence (P1 §四，P2 Task 2) ─────────────────────────

EvidenceType = Literal[
    "resource_viewed", "exercise_done", "exercise_failed",
    "tutor_question_asked", "manual_correction",
]
SourceAction = Literal["exercise", "plan", "resource", "tutor", "manual"]
EffectHint = EvidenceType


class LearningEvidence(BaseModel):
    """学习证据（P1 §4.1 十二字段）。跨域组合合法性由 evidence_contract 校验。"""

    evidence_id: str = Field(..., min_length=1, description="证据唯一标识（UUID 或 source_action:record_id:node_id）")
    student_id: int = Field(..., ge=1, description="学生 ID")
    course_id: str = Field(..., min_length=1, description="课程 ID")
    node_id: str = Field(..., min_length=1, description="知识图谱节点 ID；无归属用保留值 __none__，不得为 null")
    type: EvidenceType = Field(..., description="证据类型（P1 §4.2）")
    occurred_at: str = Field(..., min_length=1, description="学生动作发生时刻（ISO8601，非入库时刻）")
    source_action: SourceAction = Field(..., description="证据来源（P1 §4.3）")
    source_record_id: str = Field(..., min_length=1, description="产生记录的业务域 id，幂等键的一半")
    score_or_result: float | bool | str | None = Field(default=None, description="分数/对错/结果摘要")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="置信度（人工纠正 = 1.0）")
    effect_hint: EffectHint | None = Field(
        default=None, description="建议怎样影响状态，不是前端最终值",
    )
    explanation: str = Field(..., min_length=1, description="必须能解释为什么有这条记录")


class EvidenceApplyRequest(BaseModel):
    """提交证据并计算掌握度变化。Java 传入当前掌握度，Python 只算不落库。"""

    evidence: LearningEvidence = Field(..., description="待记账的学习证据")
    current_mastery: float = Field(default=0.0, ge=0.0, le=1.0, description="该节点当前掌握度（唯一真源在 Java）")


# ── Plans ────────────────────────────────────────────────────────

class CreatePlanFromPathRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    topic: str = Field(default="", description="学习主题（用户原始输入或提取的关键词）")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


class PlanStatusRequest(BaseModel):
    """Java 传入 plan 元数据 + steps 列表，Python 计算 soft_landing + decay"""
    plan: dict = Field(..., description="计划元数据 {id, user_id, status, total_steps, completed_steps, last_activity_at}")
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度（掌握度唯一真源，P1 §3.3）")


class RegressionCheckRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    answers: Optional[list[dict]] = Field(default=None, description="用户答案 [{topic, question_type, user_answer, correct_answer, choices}]")
    plan: dict = Field(default_factory=dict, description="计划元数据（Java 传入）")
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表（Java 传入）")
    days_idle: int = Field(default=0, description="计划空闲天数（Java 计算）")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度（掌握度唯一真源，P1 §3.3）")


class ReviewScheduleRequest(BaseModel):
    """Java 传入步骤列表，Python 计算复习日程"""
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表")
    days_ahead: int = Field(default=7, ge=1, le=30, description="未来 N 天")


# ── Conversation Summary ─────────────────────────────────────────

class SummaryRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="原始对话消息列表（Java 传入）")
    course_id: str = Field(default="ai_intro", description="课程 ID")


# ── Plan Steps ──────────────────────────────────────────────────────

class CompleteStepRequest(BaseModel):
    """完成一个学习步骤后触发巩固练习。"""
    step: dict = Field(..., description="当前完成的 step {step_order, topic, knowledge_node_id, status}")
    plan: dict = Field(default_factory=dict, description="计划元数据")
    steps: list[dict] = Field(default_factory=list, description="全部步骤列表")


class TodayTasksRequest(BaseModel):
    """查询今日学习任务：计算当天应完成的步骤 + 关联资源。"""
    plan: dict = Field(..., description="计划元数据 {id, total_steps, completed_steps, start_date, milestones}")
    steps: list[dict] = Field(default_factory=list, description="全部步骤列表")
    start_date: Optional[str] = Field(default=None, description="计划开始日期 ISO 字符串，缺省用当天")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度（可选）")


class ProgressUpdateRequest(BaseModel):
    """更新步骤学习进度。Java 在用户完成某步骤的学习/练习后调用。"""
    user_id: int = Field(..., ge=1, description="用户 ID")
    step_id: int = Field(default=0, description="步骤 ID")
    step_order: int = Field(default=0, description="步骤序号（step_id 为 0 时用此定位）")
    status: Literal["completed", "in_progress", "paused", "review"] = Field(default="completed", description="步骤新状态")
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="练习得分（0-1）")
    activity_type: Optional[Literal["study", "exercise", "quiz", "review"]] = Field(default="exercise", description="活动类型")
    duration_minutes: int = Field(default=0, ge=0, description="学习时长（分钟）")
    plan: dict = Field(default_factory=dict, description="计划元数据")
    steps: list[dict] = Field(default_factory=list, description="全部步骤列表")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度")


class NodeStatusChangeRequest(BaseModel):
    """知识图谱节点状态变化 → 联动计划调整。"""
    node_id: str = Field(..., min_length=1, description="状态变化的节点 ID")
    old_status: str = Field(default="", description="旧状态")
    new_status: Literal["mastered", "forgotten", "learning", "locked"] = Field(..., description="新状态")
    plan: dict = Field(default_factory=dict, description="计划元数据")
    steps: list[dict] = Field(default_factory=list, description="全部步骤列表")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度")


class ResourceLinkRequest(BaseModel):
    """为单个 plan step 生成学习资源建议（轻量版，不生成长内容）。"""
    topic: str = Field(..., min_length=1, description="步骤主题")
    knowledge_node_id: Optional[str] = Field(default=None, description="知识图谱节点 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像")


# ── Exercise Practice ──────────────────────────────────────────────

class ExerciseItem(BaseModel):
    """单道练习题（Java 传入用于分类）"""
    question: str = Field(..., min_length=1, description="题目文本")
    answer: str = Field(default="", description="答案")
    question_type: Literal["choice", "short_answer"] = Field(default="choice", description="题型")
    options: dict[str, str] = Field(default_factory=dict, description="选项 {A: xxx, B: xxx}")
    source: Literal["chat", "prebuilt", "manual"] = Field(default="chat", description="题目来源")


class CategorizeExerciseRequest(BaseModel):
    exercises: list[ExerciseItem] = Field(..., min_length=1, description="待分类的练习题列表")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    knowledge_nodes: list[dict] = Field(default_factory=list, description="当前知识图谱节点列表（Java 传入）")


class CategorizeExerciseResponse(BaseModel):
    index: int = Field(..., description="对应输入 exercise 的索引")
    knowledge_node_id: str = Field(..., description="匹配的知识节点 ID")
    difficulty: int = Field(default=3, ge=1, le=5, description="难度 1-5")
    question_type: Literal["choice", "short_answer"] = Field(default="choice")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="匹配置信度")


class PracticeRecord(BaseModel):
    """单条练习记录（Java 传入用于会话分析）"""
    knowledge_node_id: str = Field(..., min_length=1, description="知识节点 ID")
    question: str = Field(default="", description="题目文本")
    question_type: Literal["choice", "short_answer"] = Field(default="choice")
    user_answer: str = Field(default="", description="用户答案")
    correct_answer: str = Field(default="", description="正确答案")
    is_correct: bool = Field(default=False, description="是否正确")
    time_spent_seconds: int = Field(default=0, ge=0, description="耗时秒数")
    difficulty: int = Field(default=1, ge=1, le=5)


class SessionAnalyzeRequest(BaseModel):
    records: list[PracticeRecord] = Field(..., min_length=1, description="本次练习记录列表")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度")


class DashboardRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    masteries: dict[str, float] = Field(default_factory=dict, description="当前各节点掌握度")
    recent_records: list[PracticeRecord] = Field(default_factory=list, description="近期练习记录（Java 传入）")


class ProfileEnrichRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="当前学生画像（Java 传入）")
    recent_records: list[PracticeRecord] = Field(default_factory=list, description="近期练习记录")
    session_analysis: dict = Field(default_factory=dict, description="Phase C 分析结果")
