"""InquiryService — Claude-like 询问机制

资源生成模式下，用户需求模糊时先反问 2-3 个有水平的澄清问题，
而不是直接触发 6 个 Agent 全量生成。
"""

import json
import logging
from dataclasses import dataclass, field

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)

INQUIRY_SYSTEM_PROMPT = """你是一个 AI 教育助手的「需求澄清」模块。学生正在请求生成学习资源，
你需要判断需求是否足够清晰，如果不清晰则生成 2-3 个一针见血的追问。

## 判断标准（3 个维度至少 2 个明确才算"清晰"）

1. **目标明确**: 为了考试？做项目？拓展阅读？还是纯粹好奇？
2. **主题粒度合适**: "我想学机器学习"太宽，"我想理解 SVM 的核技巧及其数学推导"合适
3. **资源偏好可推断**: 能猜出需要哪类资源（讲解/练习/代码/脑图/闪卡）？

## 追问设计原则

- 一针见血：直击最关键的模糊点，不问"你是否想继续"这种废话
- 领域洞察：问题本身就是一种指引，展示你对领域知识的理解
  例: "你想从数学推导角度理解 SVM，还是更关注调参和实际应用？"
- 给出选项但让用户自由发挥：用 A/B/C 框架但不限制
- 问题间互补，不重复：一个问方向/粒度，一个问目标，一个问基础水平

## 可用资源类型
- content: 课程核心讲解（必须）
- exercise: 配套练习题
- mindmap: 思维导图
- reading: 拓展阅读推荐
- code: 代码实操案例
- flashcard: 记忆闪卡

## 输出 JSON 格式
{
  "is_clear": false,
  "clarified_topic": "用户想学的主题（提炼后）",
  "suggested_types": ["content", "exercise"],
  "level": "beginner|intermediate|advanced",
  "goal": "exam|self_study|project|curiosity",
  "questions": [
    {"text": "追问内容", "options": ["A. 选项一", "B. 选项二", "C. 选项三"]}
  ],
  "rationale": "为什么需要澄清（简短）"
}

如果需求清晰（is_clear=true），questions 为空数组，clarified_topic 和 suggested_types 必须填写。
如果不够清晰，questions 必须 2-3 个，每个 options 可选（没有合适的选项就不写）。
"""


@dataclass
class InquiryResult:
    is_clear: bool
    clarified_topic: str = ""
    suggested_types: list[str] = field(default_factory=lambda: ["content"])
    level: str = "intermediate"
    goal: str = "self_study"
    questions: list[dict] = field(default_factory=list)
    rationale: str = ""
    raw_message: str = ""


class InquiryService:
    def __init__(self, use_mock: bool | None = None):
        import os
        if use_mock is None:
            use_mock = not os.getenv("INQUIRY_USE_LLM", "").strip().lower() in ("1", "true", "yes")
        self.use_mock = use_mock

    async def check(self, message: str, student_profile: dict | None = None) -> InquiryResult:
        """检查用户需求是否清晰，不清晰则生成追问。"""
        if not message or not message.strip():
            return InquiryResult(is_clear=False, questions=[
                {"text": "你想学习什么内容？可以告诉我一个具体的主题或方向吗？"}
            ], raw_message=message)

        if self.use_mock:
            return self._mock_check(message)

        return await self._llm_check(message, student_profile or {})

    def resolve(self, original_message: str, answers: list[str],
                questions: list[dict] | None = None,
                suggested_types: list[str] | None = None,
                clarified_topic: str | None = None) -> dict:
        """合并用户答案，构造 ResourceGenRequest 所需的参数。

        优先使用客户端回传的 questions / suggested_types / clarified_topic；
        未提供时回退到合理的默认值，避免重复调用 check()。

        Returns:
            {"topic": str, "suggested_types": list[str], "context_note": str,
             "level": str, "goal": str}
        """
        context_parts = [f"原始请求: {original_message}"]
        if questions:
            for i, q in enumerate(questions):
                answer = answers[i] if i < len(answers) else ""
                context_parts.append(f"{q.get('text', '')}: {answer}")
        else:
            # 客户端未回传追问原文，无法按问题匹配，直接拼接答案
            for i, answer in enumerate(answers):
                context_parts.append(f"回答{i + 1}: {answer}")

        context_note = "\n".join(context_parts)

        suggested = list(suggested_types) if suggested_types else ["content"]
        if "content" not in suggested:
            suggested.insert(0, "content")

        return {
            "topic": clarified_topic or original_message,
            "context_note": context_note,
            "suggested_types": suggested,
            "level": "intermediate",
            "goal": "self_study",
        }

    def _mock_check(self, message: str) -> InquiryResult:
        """Mock 模式：基于消息长度和关键词做简单判断。"""
        msg = message.strip()
        # 太短或太宽泛 → 需要追问
        vague_patterns = [
            "机器学习", "深度学习", "AI", "人工智能", "编程",
            "数学", "算法", "神经网络", "数据科学",
        ]
        is_vague = len(msg) <= 8 or any(p == msg for p in vague_patterns)
        has_specifics = any(kw in msg for kw in [
            "出题", "练习", "推导", "代码", "项目", "考试",
            "思维导图", "闪卡", "阅读", "案例",
            "教程", "文档", "可视化", "对比", "排查",
            "示例", "修复", "图解", "动画", "演示",
            "实现", "入门", "生成", "整理",
        ])
        has_topic_detail = len(msg) > 10

        if has_specifics and has_topic_detail:
            return InquiryResult(
                is_clear=True,
                clarified_topic=msg,
                suggested_types=["content", "exercise", "mindmap"],
                level="intermediate",
                goal="self_study",
                raw_message=msg,
            )

        # 模糊 → 追问
        questions = []
        if is_vague or not has_topic_detail:
            questions.append({
                "text": "你想具体学习哪个方向或主题？",
                "options": [],
            })
        if not has_specifics:
            questions.append({
                "text": "你希望获得哪种类型的学习资源？",
                "options": [
                    "A. 核心知识讲解（课程文档 + 思维导图）",
                    "B. 练习题 + 记忆闪卡（适合备考）",
                    "C. 代码实操案例（适合做项目）",
                    "D. 都要，来一套完整的",
                ],
            })
        questions.append({
            "text": "你目前的基础如何？这会影响内容的深度和难度。",
            "options": [
                "A. 零基础，需要从最基础开始",
                "B. 有一些了解，但不太系统",
                "C. 基础扎实，想要进阶内容",
            ],
        })

        return InquiryResult(
            is_clear=False,
            clarified_topic=msg,
            questions=questions,
            rationale="消息较简短，缺少具体方向和资源偏好",
            raw_message=msg,
        )

    async def _llm_check(self, message: str, student_profile: dict) -> InquiryResult:
        try:
            llm = get_llm_service()
            profile_str = self._format_profile(student_profile)
            user_prompt = (
                f"学生画像: {profile_str}\n\n"
                f"学生请求: {message}\n\n"
                f"分析需求清晰度，输出 JSON："
            )
            raw = await llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=INQUIRY_SYSTEM_PROMPT,
            )
            data = parse_llm_json(raw, fallback={}, expected_key="is_clear")
            if not isinstance(data, dict):
                return self._fallback(message)

            questions = data.get("questions", [])
            if not isinstance(questions, list):
                questions = []

            suggested = data.get("suggested_types", ["content"])
            if not isinstance(suggested, list):
                suggested = ["content"]

            return InquiryResult(
                is_clear=bool(data.get("is_clear", False)),
                clarified_topic=str(data.get("clarified_topic", message)),
                suggested_types=suggested,
                level=str(data.get("level", "intermediate")),
                goal=str(data.get("goal", "self_study")),
                questions=questions,
                rationale=str(data.get("rationale", "")),
                raw_message=message,
            )
        except Exception as e:
            logger.error(f"Inquiry LLM check failed: {e}")
            return self._fallback(message)

    def _fallback(self, message: str) -> InquiryResult:
        return InquiryResult(
            is_clear=False,
            clarified_topic=message,
            questions=[
                {"text": "能再具体说说你想学什么吗？比如你关心的是概念理解、做题练习、还是代码实操？",
                 "options": ["A. 概念理解", "B. 做题练习", "C. 代码实操", "D. 都要"]},
                {"text": "你的学习目标是什么？",
                 "options": ["A. 准备考试", "B. 做项目", "C. 拓展知识面"]},
                {"text": "目前的基础大概怎样？",
                 "options": ["A. 零基础", "B. 有一些了解", "C. 基础较好"]},
            ],
            rationale="LLM 调用失败，使用通用追问",
            raw_message=message,
        )

    @staticmethod
    def _format_profile(profile: dict) -> str:
        if not profile:
            return "暂无画像"
        parts = []
        kb = profile.get("knowledge_base")
        if isinstance(kb, (int, float)):
            parts.append(f"知识基础: {kb}/100")
        goal = profile.get("learning_goal")
        if goal:
            parts.append(f"学习目标: {goal}")
        interest = profile.get("interest_direction")
        if interest:
            if isinstance(interest, str):
                val = interest
            elif isinstance(interest, list) and interest and isinstance(interest[0], dict):
                val = ", ".join(
                    i.get("text", "") for i in interest
                    if isinstance(i, dict) and i.get("status") != "archived"
                )
            else:
                val = ", ".join(str(v) for v in interest)
            if val:
                parts.append(f"兴趣方向: {val}")
        return "; ".join(parts) if parts else "暂无画像"
