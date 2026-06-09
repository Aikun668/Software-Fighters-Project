import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.llm_service import get_llm_service
from app.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)

INTENT_TYPES = Literal[
    "exercise_gen", "resource_gen", "tutor_question",
    "learning_path", "solve_problem", "flashcard_gen",
    "profile_building", "unknown",
]


class ExerciseParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    count: int = Field(default=3, ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium")


class ResourceParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)


class TutorParams(BaseModel):
    question: str = Field(..., min_length=1)


class LearningPathParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    level: Literal["beginner", "intermediate", "advanced"] = Field(default="beginner")


class SolveParams(BaseModel):
    question: str = Field(..., min_length=1)


class FlashcardParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    count: int = Field(default=5, ge=1, le=20)


class ProfileBuildingParams(BaseModel):
    message: str = Field(..., min_length=1)


PARAMS_BY_INTENT: dict[str, type[BaseModel]] = {
    "exercise_gen": ExerciseParams,
    "resource_gen": ResourceParams,
    "tutor_question": TutorParams,
    "learning_path": LearningPathParams,
    "solve_problem": SolveParams,
    "flashcard_gen": FlashcardParams,
    "profile_building": ProfileBuildingParams,
}


TOPIC_KEYWORDS = [
    "机器学习", "深度学习", "神经网络", "Python", "算法", "数据",
    "AI", "自然语言", "计算机视觉", "强化学习", "Transformer",
    "梯度", "优化", "损失函数", "正则化", "过拟合",
    "回归", "分类", "聚类", "决策树", "随机森林",
]

COUNT_PATTERN = re.compile(r"(\d+)\s*[道个题张卡]")

DIFFICULTY_EASY = {"简单", "容易", "基础", "入门"}
DIFFICULTY_HARD = {"困难", "高级", "挑战", "很难"}


@dataclass
class IntentResult:
    intent: INTENT_TYPES
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    raw_message: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class IntentDef:
    intent: INTENT_TYPES
    params_model: type[BaseModel]
    prompt: str
    keywords: list[str]
    exclusive_keywords: list[str] = field(default_factory=list)
    confidence: float = 0.85


INTENT_REGISTRY: list[IntentDef] = [
    IntentDef(
        intent="exercise_gen",
        params_model=ExerciseParams,
        prompt="用户想要生成练习题。从消息中提取：topic(主题)、count(题数,默认3)、difficulty(easy/medium/hard,默认medium)",
        keywords=["出题", "题目", "练习", "做题", "习题", "出几道", "来几道"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="resource_gen",
        params_model=ResourceParams,
        prompt="用户想要生成学习资源。从消息中提取：topic(主题)",
        keywords=["资源", "资料", "学习材料", "课件", "生成资源"],
        exclusive_keywords=["出题", "闪卡", "卡片"],
    ),
    IntentDef(
        intent="tutor_question",
        params_model=TutorParams,
        prompt="用户在问一个问题需要答疑。从消息中提取：question(完整问题文本)",
        keywords=["?", "？", "什么", "为什么", "怎么", "如何", "是什么"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="learning_path",
        params_model=LearningPathParams,
        prompt="用户想要个性化学习路径规划。从消息中提取：topic(主题)、level(beginner/intermediate/advanced,默认beginner)",
        keywords=["规划", "学习路径", "路线", "先学", "后学", "怎么学"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="solve_problem",
        params_model=SolveParams,
        prompt="用户想要逐步解一道具体的题目。从消息中提取：question(完整题目)",
        keywords=["解", "求", "算", "推导", "证明", "求解", "计算出"],
        exclusive_keywords=["解释", "概述", "介绍", "出题"],
    ),
    IntentDef(
        intent="flashcard_gen",
        params_model=FlashcardParams,
        prompt="用户想要生成记忆闪卡。从消息中提取：topic(主题)、count(卡片数,默认5)",
        keywords=["闪卡", "记忆卡", "卡片", "背"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="profile_building",
        params_model=ProfileBuildingParams,
        prompt="用户在介绍自己的学习背景、基础水平或学习目标，应进行画像构建对话",
        keywords=[
            "零基础", "新手", "刚入门", "我是", "我想学", "我的基础",
            "我刚", "刚开始", "小白", "第一次", "没学过", "不懂",
            "完全不会", "基础差", "入门", "开始学", "学习目标",
            "我想了解", "介绍一下", "我是新手", "完全不懂",
        ],
        exclusive_keywords=["出题", "做题", "练习", "闪卡", "资源", "课件"],
        confidence=0.7,
    ),
]


def _build_extraction_prompt() -> str:
    parts = ["分析用户消息，判断意图并提取参数。返回JSON。\n意图列表："]
    for i, d in enumerate(INTENT_REGISTRY, 1):
        parts.append(f"{i}. {d.intent} - {d.prompt}")
    parts.append(f"{len(INTENT_REGISTRY) + 1}. unknown - 无法识别")
    parts.append('\n返回格式：{"intent":"exercise_gen","params":{"topic":"...","count":5},"confidence":0.95}')
    return "\n".join(parts)


EXTRACTION_PROMPT = _build_extraction_prompt()


def _score_intent(message: str, intent_def: IntentDef) -> float:
    """基于关键词命中数的意图评分。exclusive_keywords 一票否决。
    注意：exclusive_keywords 基于子串匹配（`kw in msg`），可能产生边界效应。
    例如"不要出题"会因含"出题"而命中 resource_gen 的 exclusive_keywords，
    但这种简单否定句在实际对话中极少出现，当前精度可接受。"""
    msg = message.lower()
    if any(kw in msg for kw in intent_def.exclusive_keywords):
        return 0.0
    if not intent_def.keywords:
        return 0.0
    hits = sum(1 for kw in intent_def.keywords if kw in msg)
    if hits >= 3:
        return 0.9
    if hits >= 2:
        return 0.75
    if hits >= 1:
        return 0.5
    return 0.0


def _extract_topic(message: str) -> str:
    """从消息中提取主题词。先匹配预定义关键词，失败则基于分词+词长启发式提取。
    这是 mock 模式的轻量方案——不需要 LLM，但精度有限。适合快速原型阶段。"""
    for kw in TOPIC_KEYWORDS:
        if kw.lower() in message.lower():
            return kw
    # Fallback: extract CJK char sequences (2-4 chars) and alpha words
    cleaned = re.sub(r"[，。？?.!！\s、；：""''「」【】（）()]+", " ", message)
    for word in ["给我", "生成", "资源", "资料", "关于", "的", "专题",
                  "来几道", "出几道", "几张", "我想", "想要", "帮我", "请",
                  "一个", "一些", "一道", "几道"]:
        cleaned = cleaned.replace(word, " ")
    candidates = re.findall(r"[一-鿿]{2,4}|[a-zA-Z0-9]+", cleaned)
    return " ".join(candidates[:3])[:30] or "AI基础"


def _mock_extract_params(intent: INTENT_TYPES, message: str) -> dict:
    if intent == "exercise_gen":
        topic = _extract_topic(message)
        cm = COUNT_PATTERN.search(message)
        count = int(cm.group(1)) if cm else 3
        difficulty = "medium"
        if any(kw in message for kw in DIFFICULTY_EASY):
            difficulty = "easy"
        elif any(kw in message for kw in DIFFICULTY_HARD):
            difficulty = "hard"
        return {"topic": topic, "count": count, "difficulty": difficulty}

    if intent == "resource_gen":
        return {"topic": _extract_topic(message)}

    if intent == "tutor_question":
        return {"question": message.strip()}

    if intent == "learning_path":
        return {"topic": _extract_topic(message), "level": "beginner"}

    if intent == "solve_problem":
        return {"question": message.strip()}

    if intent == "flashcard_gen":
        topic = _extract_topic(message)
        cm = COUNT_PATTERN.search(message)
        count = int(cm.group(1)) if cm else 5
        return {"topic": topic, "count": count}

    if intent == "profile_building":
        return {"message": message.strip()}

    return {}


class IntentExtractor:
    def __init__(self, use_mock: bool | None = None):
        if use_mock is None:
            use_mock = not os.getenv("INTENT_USE_LLM", "").strip().lower() in ("1", "true", "yes")
        self.use_mock = use_mock

    async def extract(self, message: str) -> IntentResult:
        if not message or not message.strip():
            return IntentResult(intent="unknown", raw_message=message)

        if self.use_mock:
            return self._extract_mock(message)

        return await self._extract_llm(message)

    def _extract_mock(self, message: str) -> IntentResult:
        scored = [
            (_score_intent(message, d), d) for d in INTENT_REGISTRY
        ]
        scored.sort(key=lambda x: -x[0])

        best_score, best_def = scored[0]

        if best_score >= 0.3:
            params = _mock_extract_params(best_def.intent, message)
            model = PARAMS_BY_INTENT.get(best_def.intent)
            if model:
                try:
                    validated = model(**params)
                    return IntentResult(
                        intent=best_def.intent,
                        params=validated.model_dump(),
                        confidence=min(best_score * 0.7 + 0.3, 0.95),
                        raw_message=message,
                    )
                except ValidationError as e:
                    errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
                    return IntentResult(
                        intent=best_def.intent,
                        params=params,
                        confidence=best_score * 0.4,
                        raw_message=message,
                        errors=errors,
                    )

        return IntentResult(
            intent="tutor_question",
            params={"question": message.strip()},
            confidence=0.5,
            raw_message=message,
        )

    async def _extract_llm(self, message: str) -> IntentResult:
        try:
            llm = get_llm_service()
            prompt = EXTRACTION_PROMPT + f"\n\n用户消息：{message}\n\n解析意图，返回JSON："
            response = await llm.chat([{"role": "user", "content": prompt}])
            data = parse_llm_json(response, fallback={}, expected_key="intent")
            if not isinstance(data, dict) or "intent" not in data:
                return IntentResult(intent="unknown", raw_message=message)

            intent = data.get("intent", "unknown")
            params = data.get("params", {})
            model = PARAMS_BY_INTENT.get(intent)
            if model:
                try:
                    validated = model(**params)
                    params = validated.model_dump()
                except ValidationError as e:
                    errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
                    return IntentResult(
                        intent=intent,
                        params=params,
                        confidence=data.get("confidence", 0.0),
                        raw_message=message,
                        errors=errors,
                    )

            try:
                conf = float(data.get("confidence", 0.0))
            except (ValueError, TypeError):
                conf = 0.0
            return IntentResult(
                intent=intent,
                params=params,
                confidence=conf,
                raw_message=message,
            )
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            return IntentResult(intent="unknown", raw_message=message)