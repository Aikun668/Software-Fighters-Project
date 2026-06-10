"""Pydantic request models — Architecture #2: Java 在请求体中传入所有数据"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


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
    topic: str = Field(..., min_length=1, description="资源主题")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


class ExportPptxRequest(BaseModel):
    content_blocks: list = Field(default_factory=list, description="PPT 内容块")
    title: str = Field(default="AI学习资源", description="PPT 标题")


# ── Tutor ──────────────────────────────────────────────────────

class TutorChatRequest(BaseModel):
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    messages: list[dict] = Field(..., min_length=1, description="完整对话消息数组（Java 传入）")


# ── Exercise ───────────────────────────────────────────────────

class ExerciseGenRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="题目主题")
    count: int = Field(default=3, ge=1, le=20, description="题目数量")
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium", description="难度")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")
    user_id: int = Field(default=1, description="用户 ID")


class GradeRequest(BaseModel):
    type: Literal["choice", "short_answer"] = Field(..., description="题目类型")
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
    mode: Literal["tutor", "resource", "solve", "exercise", "research", "auto"] = Field(
        default="auto", description="对话模式: auto=自动感知, tutor=答疑, resource=资源, solve=解题, exercise=练习, research=研究"
    )
    conversation_id: Optional[int] = Field(default=None, description="会话 ID（Java 传入，仅供参考）")
    style: Optional[Literal["standard", "socratic"]] = Field(default="standard", description="tutor 子风格")
    messages: list[dict] = Field(default_factory=list, description="历史消息列表（Java 传入）")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


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


# ── Plans ────────────────────────────────────────────────────────

class CreatePlanFromPathRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（Java 传入）")


class PlanStatusRequest(BaseModel):
    """Java 传入 plan 元数据 + steps 列表，Python 计算 soft_landing + decay"""
    plan: dict = Field(..., description="计划元数据 {id, user_id, status, total_steps, completed_steps, last_activity_at}")
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表")


class RegressionCheckRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    answers: Optional[list[dict]] = Field(default=None, description="用户答案 [{topic, question_type, user_answer, correct_answer, choices}]")
    plan: dict = Field(default_factory=dict, description="计划元数据（Java 传入）")
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表（Java 传入）")
    days_idle: int = Field(default=0, description="计划空闲天数（Java 计算）")


class ReviewScheduleRequest(BaseModel):
    """Java 传入步骤列表，Python 计算复习日程"""
    steps: list[dict] = Field(default_factory=list, description="计划步骤列表")
    days_ahead: int = Field(default=7, ge=1, le=30, description="未来 N 天")


# ── Conversation Summary ─────────────────────────────────────────

class SummaryRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="原始对话消息列表（Java 传入）")
    course_id: str = Field(default="ai_intro", description="课程 ID")
