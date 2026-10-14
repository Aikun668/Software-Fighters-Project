"""意图关键词表与二级意图抽取能力。

【决策所有权】意图关键词表的唯一来源 —— `INTENT_REGISTRY`（10 类 `IntentDef`）。
  - 该表被 `RouterAgent._keyword_route` 借用做二级分发；`RouterAgent` **不另建表**
  - ⚠️ `IntentExtractor.extract / extract_multi` 当前**未接入线上管线**
    （仅测试与 `internal_api._get_intent_extractor` 装配工厂引用）
  - 禁止：在此选择 Center；禁止决定一级路径（属 `CapabilityGate`）
  - 约定：`temp_file/9.15工程改造计划/0、产品方向与约束/三类决策与命名约定.md`
"""

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
    "profile_building", "code_example",
    "visualize", "knowledge_graph", "diagnose", "unknown",
]

class ExerciseParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    count: int = Field(default=3, ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium")


class ResourceParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)


class TutorParams(BaseModel):
    question: str = Field(..., min_length=1)


class CodeExampleParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    language: str = Field(default="python")


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


class VisualizeParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    viz_type: str = Field(default="auto")


class KnowledgeGraphParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    depth: int = Field(default=2, ge=1, le=4)


class DiagnoseParams(BaseModel):
    topic: str = Field(default="AI基础", min_length=1)
    skills: list[str] = Field(default_factory=list)
    prior_mastery: dict[str, float] = Field(default_factory=dict)
    attempts: list[dict] = Field(default_factory=list)


PARAMS_BY_INTENT: dict[str, type[BaseModel]] = {
    "exercise_gen": ExerciseParams,
    "resource_gen": ResourceParams,
    "tutor_question": TutorParams,
    "code_example": CodeExampleParams,
    "learning_path": LearningPathParams,
    "solve_problem": SolveParams,
    "flashcard_gen": FlashcardParams,
    "profile_building": ProfileBuildingParams,
    "visualize": VisualizeParams,
    "knowledge_graph": KnowledgeGraphParams,
    "diagnose": DiagnoseParams,
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
class MultiIntentResult:
    intents: list[IntentResult] = field(default_factory=list)
    is_clear: bool = True
    inquiry_question: str = ""
    raw_message: str = ""


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
        keywords=["出题", "题目", "练习", "做题", "习题", "出几道", "来几道",
                  "练习题", "选择题", "计算题", "填空题", "简答题"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="resource_gen",
        params_model=ResourceParams,
        prompt="用户想要生成学习资源。从消息中提取：topic(主题)",
        keywords=["资源", "资料", "学习材料", "课件", "生成资源",
                  "大纲", "讲义", "教程", "文档", "提纲", "幻灯片", "对比", "项目",
                  "思维导图", "脑图", "概念图"],
        exclusive_keywords=["出题", "闪卡", "卡片"],
    ),
    IntentDef(
        intent="code_example",
        params_model=CodeExampleParams,
        prompt="用户想要代码示例。从消息中提取：topic(主题)、language(编程语言,默认python)",
        keywords=["代码", "例子", "示例", "代码示例", "写一个", "怎么写", "实现", "写个", "编程"],
        exclusive_keywords=["出题"],
    ),
    IntentDef(
        intent="tutor_question",
        params_model=TutorParams,
        prompt="用户在问一个问题需要答疑。从消息中提取：question(完整问题文本)",
        keywords=["什么", "为什么", "怎么", "如何", "是什么",
                  "解释", "讲讲", "讲解", "说说", "介绍",
                  "告诉我", "说明", "分析一下", "帮我理解"],
        exclusive_keywords=[],
        confidence=0.6,  # 2 命中: 0.75×0.6=0.45 > 0.4 阈值；单命中: 0.5×0.6=0.30 仍过滤
    ),
    IntentDef(
        intent="learning_path",
        params_model=LearningPathParams,
        prompt="用户想要个性化学习路径规划。从消息中提取：topic(主题)、level(beginner/intermediate/advanced,默认beginner)",
        keywords=["规划", "学习路径", "路线", "先学", "后学", "怎么学",
                  "计划", "安排", "学习安排", "自学", "学习计划"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="solve_problem",
        params_model=SolveParams,
        prompt="用户想要逐步解一道具体的题目。从消息中提取：question(完整题目)",
        keywords=["解题", "求解", "计算", "求导", "解方程", "推导", "证明", "计算出", "这道题", "帮我解"],
        exclusive_keywords=["解释", "概述", "介绍", "出题"],
    ),
    IntentDef(
        intent="flashcard_gen",
        params_model=FlashcardParams,
        prompt="用户想要生成记忆闪卡。从消息中提取：topic(主题)、count(卡片数,默认5)",
        keywords=["闪卡", "记忆卡", "卡片", "背诵", "背一下"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="visualize",
        params_model=VisualizeParams,
        prompt="用户希望生成图表、流程图或可视化内容。从消息中提取：topic(主题)",
        keywords=["画图", "图表", "流程图", "可视化", "画一下", "画一张",
                  "画出", "画个图", "绘制", "结构图", "架构图", "对比图",
                  "曲线图", "示意图"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="knowledge_graph",
        params_model=KnowledgeGraphParams,
        prompt="用户希望查看知识图谱。从消息中提取：topic(主题)、depth(深度,默认2)",
        keywords=["知识图谱", "图谱", "关系图", "知识结构"],
        exclusive_keywords=[],
    ),
    IntentDef(
        intent="diagnose",
        params_model=DiagnoseParams,
        prompt="用户希望进行学习诊断或测试自己的掌握情况。从消息中提取：topic(主题)、skills(技能列表)",
        keywords=["诊断", "测试", "掌握", "薄弱", "测一下", "考核", "测验", "摸底", "检查一下"],
        exclusive_keywords=["解题", "求解"],
        confidence=0.8,
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
            "学过", "基础", "方向", "迷茫", "不知道怎么",
            "我不知道", "大二", "大一", "大三", "大四", "转行",
        ],
        exclusive_keywords=["出题", "做题", "练习", "闪卡", "资源", "课件"],
        confidence=0.7,
    ),
]


def _build_extraction_prompt() -> str:
    """构建精简版 LLM 提取 prompt — 5 大类意图。

    细粒度路由（解题/诊断/画像）由 RouterAgent 关键词粗路由处理，
    LLM 只需判断消息属于哪个 Center，大幅降低分类难度。
    """
    parts = [
        "分析用户消息，判断其意图类别。返回JSON。",
        "",
        "规则：",
        "1. 只提取用户明确表达的意图，不推测",
        "2. 单意图消息只输出一个意图，多诉求消息（如'解释X再出几道题'）才输出多个",
        "3. 不确定时用 tutor_question 兜底",
        "",
        "意图类别（5类）：",
        "1. tutor_question - 答疑/概念解释/闲聊/问为什么/问怎么做",
        "2. resource_gen - 生成学习资源（教程/文档/代码/闪卡/思维导图/项目）",
        "3. exercise_gen - 生成练习题/出题/做题",
        "4. learning_path - 学习路径规划/学习路线/怎么学",
        "5. visualize - 画图/可视化/流程图/知识图谱",
        "6. unknown - 无法识别",
        "",
        '返回格式：{"intents":[{"intent":"exercise_gen","params":{"topic":"...","count":5},"confidence":0.95}],"is_clear":true}',
        "is_clear 表示意图是否清晰可执行；模糊设为 false。",
    ]
    return "\n".join(parts)


EXTRACTION_PROMPT = _build_extraction_prompt()

# 意图互斥组：同组内只保留置信度最高的那个，过滤 LLM 噪声
# 意图优先级：同分组内同分时高优先级胜出（数值越大越优先）
_INTENT_PRIORITY: dict[str, int] = {
    "visualize": 10,         # 可视化请求优先于资源生成
    "solve_problem": 5,      # 解题优先于出题
}
# 注意：不要把跨功能域的意图放在同组，否则会误杀真多意图
_MUTEX_GROUPS: list[set[str]] = [
    {"solve_problem", "exercise_gen"},  # 解题 vs 出题（真冲突：解现有题和出新题互斥）
    {"visualize", "resource_gen"},      # 可视化优先：防 ContentAgent 的 summary 污染管线输入
]


def _apply_mutex_filter(intents: list["IntentResult"]) -> list["IntentResult"]:
    """后置互斥过滤：LLM 多输出的意图进入同组时只留最高置信度。"""
    if len(intents) <= 1:
        return intents

    result: list[IntentResult] = list(intents)
    for group in _MUTEX_GROUPS:
        matched = [i for i in result if i.intent in group]
        if len(matched) > 1:
            best = max(matched, key=lambda i: i.confidence)
            result = [i for i in result if i not in matched or i is best]
    return result


def _score_intent(message: str, intent_def: IntentDef) -> float:
    """基于关键词命中数的意图评分。exclusive_keywords 一票否决。
    confidence 作为评分乘数：tutor_question(0.5) 等低频意图单次命中不出头，
    只有多关键词命中才能与其他意图竞争。"""
    msg = message.lower()
    if any(kw in msg for kw in intent_def.exclusive_keywords):
        return 0.0
    if not intent_def.keywords:
        return 0.0
    hits = sum(1 for kw in intent_def.keywords if kw in msg)
    if hits >= 3:
        base = 0.9
    elif hits >= 2:
        base = 0.75
    elif hits >= 1:
        base = 0.5
    else:
        return 0.0
    return base * intent_def.confidence


def _extract_topic(message: str) -> str:
    for kw in TOPIC_KEYWORDS:
        if kw.lower() in message.lower():
            return kw
    cleaned = re.sub(r"[，。？?.!！\s、；：""''「」【】（）()]+", " ", message)
    for word in ["给我", "生成", "资源", "资料", "关于", "的", "专题",
                  "来几道", "出几道", "几张", "我想", "想要", "帮我", "请",
                  "一个", "一些", "一道", "几道", "规划", "路径", "学习路径",
                  "并", "一下"]:
        cleaned = cleaned.replace(word, " ")
    candidates = re.findall(r"[一-鿿]{2,4}|[a-zA-Z0-9]+", cleaned)
    return " ".join(candidates[:3])[:30] or message[:30] or "AI基础"


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

    if intent == "diagnose":
        return {
            "topic": _extract_topic(message),
            "skills": [_extract_topic(message)],
            "prior_mastery": {},
            "attempts": [],
        }

    return {}


class IntentExtractor:
    def __init__(self, use_mock: bool | None = None):
        if use_mock is None:
            use_mock = not os.getenv("INTENT_USE_LLM", "").strip().lower() in ("1", "true", "yes")
        self.use_mock = use_mock

    async def extract(self, message: str) -> IntentResult:
        if not message or not message.strip():
            return IntentResult(intent="unknown", raw_message=message)

        multi_result = await self.extract_multi(message)
        if multi_result.intents:
            return multi_result.intents[0]
        return IntentResult(intent="unknown", raw_message=message)

    async def extract_multi(
        self,
        message: str,
        max_intents: int = 3,
        clarity_threshold: float = 0.5,
    ) -> MultiIntentResult:
        if not message or not message.strip():
            return MultiIntentResult(
                intents=[IntentResult(intent="unknown", raw_message=message)],
                is_clear=False,
                inquiry_question="你想了解什么？",
                raw_message=message,
            )

        if self.use_mock:
            result = self._extract_multi_mock(message, max_intents, clarity_threshold)
        else:
            result = await self._extract_multi_llm(message, max_intents, clarity_threshold)

        # 后置互斥过滤：LLM 多输出的意图进同组只留最高置信度
        result.intents = _apply_mutex_filter(result.intents)
        return result

    def _extract_multi_mock(
        self,
        message: str,
        max_intents: int,
        clarity_threshold: float,
    ) -> MultiIntentResult:
        scored = [(_score_intent(message, d), d) for d in INTENT_REGISTRY]
        scored.sort(key=lambda x: -x[0])

        selected: list[IntentResult] = []
        for score, intent_def in scored:
            if score < 0.3:
                continue
            params = _mock_extract_params(intent_def.intent, message)
            model = PARAMS_BY_INTENT.get(intent_def.intent)
            if model:
                try:
                    validated = model(**params)
                    params = validated.model_dump()
                except ValidationError as e:
                    errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
                    selected.append(IntentResult(
                        intent=intent_def.intent,
                        params=params,
                        confidence=score * 0.4,
                        raw_message=message,
                        errors=errors,
                    ))
                    continue
            selected.append(IntentResult(
                intent=intent_def.intent,
                params=params,
                confidence=min(score * 0.7 + 0.3, 0.95),
                raw_message=message,
            ))
            if len(selected) >= max_intents:
                break

        if not selected:
            selected.append(IntentResult(
                intent="tutor_question",
                params={"question": message.strip()},
                confidence=0.5,
                raw_message=message,
            ))

        best_confidence = selected[0].confidence
        is_clear = best_confidence >= clarity_threshold

        return MultiIntentResult(
            intents=selected,
            is_clear=is_clear,
            inquiry_question=self._build_inquiry_question(selected),
            raw_message=message,
        )

    async def _extract_multi_llm(
        self,
        message: str,
        max_intents: int,
        clarity_threshold: float,
    ) -> MultiIntentResult:
        try:
            llm = get_llm_service()
            prompt = EXTRACTION_PROMPT + f"\n\n用户消息：{message}\n\n解析意图，返回JSON："
            response = await llm.chat([{"role": "user", "content": prompt}])
            data = parse_llm_json(response, fallback={}, expected_key="intents")

            if not isinstance(data, dict):
                return self._fallback_multi(message)

            raw_intents = data.get("intents")
            if raw_intents is None and "intent" in data:
                raw_intents = [data]
            if not isinstance(raw_intents, list):
                raw_intents = [raw_intents] if isinstance(raw_intents, dict) else []

            selected: list[IntentResult] = []
            for item in raw_intents[:max_intents]:
                if not isinstance(item, dict):
                    continue
                intent = item.get("intent", "unknown")
                params = item.get("params", {})
                model = PARAMS_BY_INTENT.get(intent)
                if model:
                    try:
                        validated = model(**params)
                        params = validated.model_dump()
                    except ValidationError as e:
                        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
                        selected.append(IntentResult(
                            intent=intent,
                            params=params,
                            confidence=float(item.get("confidence", 0.0)) * 0.5,
                            raw_message=message,
                            errors=errors,
                        ))
                        continue
                selected.append(IntentResult(
                    intent=intent,
                    params=params,
                    confidence=float(item.get("confidence", 0.0)),
                    raw_message=message,
                ))

            if not selected:
                return self._fallback_multi(message)

            is_clear = data.get("is_clear", True)
            if not isinstance(is_clear, bool):
                is_clear = selected[0].confidence >= clarity_threshold

            return MultiIntentResult(
                intents=selected,
                is_clear=is_clear,
                inquiry_question=data.get("inquiry_question") or self._build_inquiry_question(selected),
                raw_message=message,
            )
        except Exception as e:
            logger.error(f"Multi-intent extraction failed: {e}")
            return self._fallback_multi(message)

    def _fallback_multi(self, message: str) -> MultiIntentResult:
        result = IntentResult(
            intent="tutor_question",
            params={"question": message.strip()},
            confidence=0.5,
            raw_message=message,
        )
        return MultiIntentResult(
            intents=[result],
            is_clear=False,
            inquiry_question=self._build_inquiry_question([result]),
            raw_message=message,
        )

    @staticmethod
    def _build_inquiry_question(intents: list[IntentResult]) -> str:
        if not intents:
            return "你想了解什么？"
        intent_names = [r.intent for r in intents]
        if len(intent_names) == 1:
            return f"检测到你可能有【{intent_names[0]}】的需求，需要我帮你处理吗？"
        return f"检测到你可能有多个需求：{', '.join(intent_names)}，想先处理哪个？"