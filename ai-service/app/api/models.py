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


# ── Evaluation ─────────────────────────────────────────────────

class EvaluationReportRequest(BaseModel):
    evaluation_results: dict = Field(..., description="评估结果")
    user_id: Optional[int] = Field(default=None, description="用户 ID（提供则触发画像增量更新）")
