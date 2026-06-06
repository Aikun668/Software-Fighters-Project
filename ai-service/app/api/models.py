"""Pydantic request models — 替换所有 request: Request 的裸 JSON 解析"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Profile ────────────────────────────────────────────────────

class ProfileChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="对话消息数组 [{role, content}]")
    user_id: int = Field(default=1, description="用户 ID")


# ── Resources ──────────────────────────────────────────────────

class ResourceGenRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="资源主题")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（可选，后端会自动加载）")


class ExportPptxRequest(BaseModel):
    content_blocks: list = Field(default_factory=list, description="PPT 内容块")
    title: str = Field(default="AI学习资源", description="PPT 标题")


# ── Tutor ──────────────────────────────────────────────────────

class TutorChatRequest(BaseModel):
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像")
    content: Optional[str] = Field(default=None, description="【新 API】当前消息文本")
    messages: Optional[list[dict]] = Field(default=None, description="【旧 API】完整消息数组")
    conversation_id: Optional[int] = Field(default=None, description="【新 API】会话 ID")


# ── Exercise ───────────────────────────────────────────────────

class ExerciseGenRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="题目主题")
    count: int = Field(default=3, ge=1, le=20, description="题目数量")
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium", description="难度")
    student_profile: dict = Field(default_factory=dict, description="学生画像")
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
    user_id: Optional[int] = Field(default=None, description="用户 ID（提供则触发画像增量更新）")


class UnifiedChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户自然语言输入")
    user_id: int = Field(default=1, description="用户 ID")
    mode: Literal["tutor", "resource", "solve", "exercise", "research", "auto"] = Field(
        default="auto", description="对话模式: auto=自动感知, tutor=答疑, resource=资源, solve=解题, exercise=练习, research=研究"
    )
    conversation_id: Optional[int] = Field(default=None, description="会话 ID，所有模式共享同一会话")
    style: Optional[Literal["standard", "socratic"]] = Field(default="standard", description="tutor 子风格: standard=标准, socratic=苏格拉底引导")


# ── Inquiry ──────────────────────────────────────────────────────

class InquiryResolveRequest(BaseModel):
    original_message: str = Field(..., min_length=1, description="原始用户消息")
    answers: list[str] = Field(..., min_length=1, description="用户对追问的回答列表")
    user_id: int = Field(default=1, description="用户 ID")
    student_profile: dict = Field(default_factory=dict, description="学生画像（可选）")
    questions: list[dict] = Field(default_factory=list, description="追问列表（客户端回传，用于构造上下文）")
    suggested_types: list[str] = Field(default_factory=list, description="推荐的资源类型（客户端回传）")
    clarified_topic: str = Field(default="", description="澄清后的主题（客户端回传）")


# ── Knowledge Graph ──────────────────────────────────────────────


class PlanCreateRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    course_id: str = Field(default="ai_intro", description="课程 ID")
    steps: list[dict] = Field(..., min_length=1, description="学习路径步骤列表")
    concept_graph: dict = Field(default_factory=dict, description="知识图谱数据")


class CreatePlanFromPathRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    course_id: str = Field(default="ai_intro", description="课程 ID")


class PlanProgressRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    step_id: int = Field(..., ge=1, description="步骤 ID")
    status: str = Field(default="completed", description="步骤状态: pending|in_progress|completed|paused|review")
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="练习得分 0-1")
    activity_type: str = Field(default="study", description="活动类型: study|exercise|review|quiz")
    duration_minutes: int = Field(default=0, ge=0, description="学习时长（分钟）")


class PlanResumeRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")


class RegressionCheckRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    answers: Optional[list[dict]] = Field(default=None, description="用户答案 [{step_id, question_id, user_answer}]")


class NodeStatusChangeRequest(BaseModel):
    user_id: int = Field(..., ge=1, description="用户 ID")
    node_id: str = Field(..., min_length=1, description="知识图谱节点 ID")
    old_status: str = Field(..., description="旧状态")
    new_status: str = Field(..., description="新状态")
