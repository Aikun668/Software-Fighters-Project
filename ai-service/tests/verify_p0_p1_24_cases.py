"""P0+P1 联合测试：Router + TutorAgent 24 例梯度暴力测试。

用法:
    cd ai-service && PYTHONPATH=. python tests/verify_p0_p1_24_cases.py

设计:
  - P0 (12 例): 离线关键词路由，直接调 RouterAgent，不经过 HTTP
  - P1 (8 例):  真实 LLM 调用 TutorAgent → flash LLM 做质量评估 (LLM-as-Judge)
  - Combined (4 例): RouterAgent 路由 + TutorAgent 执行 → judge 评估
  - 评分引擎: P0 关键词评分 + P1/Combined LLM-as-Judge 五维评分
  - 加权总分 > 90 为 PASS
"""
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# 抑制 SafetyPipeline 日志噪声
import logging
logging.getLogger("app.utils.content_guard").setLevel(logging.ERROR)
logging.getLogger("app.utils.security_logger").setLevel(logging.ERROR)

# ── LLM-as-Judge 初始化 ────────────────────────────────────────────────
# 复用 PROFILE_DIRECTOR 的 MiniMax-M3 通道
# 与 profile_agent.semantic_judge 共享同一条低成本快速通道

from app.services.llm_service import PROFILE_DIRECTOR, OpenAILLM
from app.utils.prompt_loader import interpolate_variables, build_prompt

_judge_llm = None
_judge_system_template: str = ""
_judge_user_template: str = ""

JUDGE_RESPONSE_MAX_CHARS = 2800  # 截断回答，控制 judge prompt 长度


def _init_judge():
    """延迟初始化 judge LLM，避免 import 时触发 ChromaDB 加载。"""
    global _judge_llm, _judge_system_template, _judge_user_template
    cfg = PROFILE_DIRECTOR.default
    _judge_llm = OpenAILLM(
        temperature=cfg.temperature,
        max_tokens=512,
        use_mock=False,
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
    )
    _judge_system_template = build_prompt(
        "tutor_agent", filename="quality_judge.yaml", key="system",
    )
    _judge_user_template = build_prompt(
        "tutor_agent", filename="quality_judge.yaml", key="user",
    )


async def judge_quality(question: str, difficulty: int, response: str) -> dict | None:
    """调用 flash LLM 对回答质量做 5 维评分。失败时返回 None，调用方应回退关键词评分。"""
    global _judge_llm, _judge_system_template, _judge_user_template
    if _judge_llm is None:
        try:
            _init_judge()
        except Exception as e:
            logging.getLogger(__name__).warning("Judge LLM init failed: %s", e)
            return None

    truncated = response[:JUDGE_RESPONSE_MAX_CHARS]
    user_prompt = interpolate_variables(
        _judge_user_template,
        {"question": question, "difficulty": str(difficulty), "response": truncated},
    )
    try:
        result_text = await _judge_llm.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=_judge_system_template,
        )
        # 解析 JSON（容忍 markdown code fence）
        text = result_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        judge_result = json.loads(text)
        if not isinstance(judge_result, dict) or "total" not in judge_result:
            return None
        return judge_result
    except Exception as e:
        logging.getLogger(__name__).warning("Judge LLM call failed: %s", e)
        return None


def _judge_to_details(j: dict, elapsed_ms: float) -> dict:
    """将 judge JSON 转为兼容 ScoringEngine.score_tutor 的 details 格式。"""
    return {
        "judge_accuracy": j.get("accuracy", 0),
        "judge_depth": j.get("depth", 0),
        "judge_helpfulness": j.get("helpfulness", 0),
        "judge_structure": j.get("structure", 0),
        "judge_domain_fit": j.get("domain_fit", 0),
        "judge_total": j.get("total", 0),
        "judge_brief": j.get("brief", ""),
        "elapsed_ms": round(elapsed_ms, 1),
    }


# ── Test case definitions ──────────────────────────────────────────────

# P0 Router 用例 (离线) — 12 例
# 每个用例: id, difficulty, message, expected_intents (list), expected_centers (set)
# 评分维度: intent(50) + center(30) + multi(10) + params(10)
P0_CASES = [
    {
        "id": 1, "difficulty": 1, "message": "什么是机器学习？",
        "expected_intents": ["tutor_question"],
        "expected_centers": {"auto"},
        "desc": "单关键词命中，基础答疑路由",
    },
    {
        "id": 2, "difficulty": 1, "message": "帮我出 5 道 Python 练习题",
        "expected_intents": ["exercise_gen"],
        "expected_centers": {"exercise"},
        "desc": "数字提取+关键词匹配",
    },
    {
        "id": 3, "difficulty": 1, "message": "画一张神经网络结构图",
        "expected_intents": ["visualize"],
        "expected_centers": {"visualization"},
        "desc": "可视化关键词精确匹配",
    },
    {
        "id": 4, "difficulty": 1, "message": "我是零基础，想学 AI",
        "expected_intents": ["profile_building"],
        "expected_centers": {"auto"},
        "desc": "自我描述→画像构建",
    },
    {
        "id": 5, "difficulty": 2, "message": "帮我规划学习 Python 的路线",
        "expected_intents": ["learning_path"],
        "expected_centers": {"plan"},
        "desc": "学习路径关键词",
    },
    {
        "id": 6, "difficulty": 2, "message": "生成机器学习的思维导图",
        "expected_intents": ["resource_gen"],
        "expected_centers": {"resource"},
        "desc": "思维导图→资源中心",
    },
    {
        "id": 7, "difficulty": 2, "message": "帮我解这道题：求 f(x)=x²+3x 的导数",
        "expected_intents": ["solve_problem"],
        "expected_centers": {"auto"},
        "desc": "解题关键词（互斥组：解题 vs 答疑）",
    },
    {
        "id": 8, "difficulty": 2, "message": "我想诊断一下我的算法基础",
        "expected_intents": ["diagnose"],
        "expected_centers": {"auto"},
        "desc": "诊断关键词匹配",
    },
    {
        "id": 9, "difficulty": 3,
        "message": "什么是梯度下降，怎么解释，为什么重要，画个示意图，再出几道练习题",
        "expected_intents": ["tutor_question", "visualize", "exercise_gen"],
        "expected_centers": {"auto", "visualization", "exercise"},
        "desc": "多意图提取+排序（答疑+画图+出题 3 意图）",
    },
    {
        "id": 10, "difficulty": 3,
        "message": "帮我诊断薄弱点，生成学习资料，再来几道练习题检验",
        "expected_intents": ["diagnose", "resource_gen", "exercise_gen"],
        "expected_centers": {"auto", "resource", "exercise"},
        "desc": "多意图链式解析（诊断+资源+练习，无互斥冲突）",
    },
    {
        "id": 11, "difficulty": 3,
        "message": "帮我解这道题并出几道类似的练习",
        "expected_intents": ["exercise_gen"],  # solve_problem 被 mutex 淘汰
        "expected_centers": {"exercise"},
        "desc": "mutex 互斥组冲突：解题 vs 出题 → 保留高置信度",
        "mutex_expected": True,
        "mutex_dropped": "solve_problem",
    },
    {
        "id": 12, "difficulty": 3,
        "message": "今天天气不错",
        "expected_intents": ["tutor_question"],
        "expected_centers": {"auto"},
        "desc": "无关键词匹配→兜底路由（tutor_question fallback）",
    },
]

# P1 TutorAgent 用例 (需要真实 LLM) — 8 例
# 每个用例: id, difficulty, message, required_keywords, optional_keywords, forbidden_patterns
P1_CASES = [
    {
        "id": 13, "difficulty": 1,
        "message": "什么是过拟合？",
        "required_keywords": ["过拟合", "泛化", "训练"],
        "optional_keywords": ["正则化", "验证集", "测试集", "偏差", "方差"],
        "forbidden_patterns": [],
        "desc": "基础概念解释",
        "is_ai_domain": True,
    },
    {
        "id": 14, "difficulty": 1,
        "message": "Python 的 list 和 tuple 有什么区别？",
        "required_keywords": ["可变", "不可变"],
        "optional_keywords": ["性能", "哈希", "元组", "列表", "内存"],
        "forbidden_patterns": [],
        "desc": "通用知识（非 AI 领域）",
        "is_ai_domain": False,
    },
    {
        "id": 15, "difficulty": 2,
        "message": "反向传播算法的原理是什么？",
        "required_keywords": ["梯度", "链式"],
        "optional_keywords": ["反向传播", "前向", "更新", "权重", "损失", "偏导"],
        "forbidden_patterns": [],
        "desc": "KB 召回 + AI 知识",
        "is_ai_domain": True,
    },
    {
        "id": 16, "difficulty": 2,
        "message": "CNN 和 Transformer 的核心区别是什么？",
        "required_keywords": ["CNN", "Transformer"],
        "optional_keywords": ["卷积", "注意力", "局部", "全局", "序列", "图像"],
        "forbidden_patterns": [],
        "desc": "对比分析类问题",
        "is_ai_domain": True,
    },
    {
        "id": 17, "difficulty": 2,
        "message": "怎么学机器学习？",
        "required_keywords": ["数学", "实践"],
        "optional_keywords": ["Python", "课程", "项目", "基础", "入门", "资源"],
        "forbidden_patterns": [],
        "desc": "学习建议（非技术）",
        "is_ai_domain": True,
    },
    {
        "id": 18, "difficulty": 3,
        "message": "为什么我的神经网络训练 loss 不下降？",
        "required_keywords": ["学习率", "梯度"],
        "optional_keywords": ["消失", "爆炸", "初始化", "数据", "归一化", "架构"],
        "forbidden_patterns": [],
        "desc": "诊断推理型（需列举多原因）",
        "is_ai_domain": True,
    },
    {
        "id": 19, "difficulty": 3,
        "message": "用简单例子解释梯度下降，再解释为什么学习率太大会导致不收敛",
        "required_keywords": ["梯度下降", "学习率"],
        "optional_keywords": ["收敛", "震荡", "发散", "步长", "最小值", "局部最优"],
        "forbidden_patterns": [],
        "desc": "多步解释 + 深度追问",
        "is_ai_domain": True,
    },
    {
        "id": 20, "difficulty": 3,
        "message": "GAN 的生成器和判别器是如何对抗训练的？用博弈论角度解释",
        "required_keywords": ["生成器", "判别器", "对抗"],
        "optional_keywords": ["博弈", "纳什均衡", "零和", "minimax", "伪造", "鉴别"],
        "forbidden_patterns": [],
        "desc": "跨领域深度（AI + 博弈论）",
        "is_ai_domain": True,
    },
]

# Combined 联合管线用例 — 4 例
COMBINED_CASES = [
    {
        "id": 21, "difficulty": 1,
        "message": "什么是卷积神经网络？",
        "expected_intents": ["tutor_question"],
        "expected_centers": {"auto"},
        "tutor_keywords": ["卷积", "CNN", "特征"],
        "tutor_optional": ["池化", "滤波器", "感受野", "通道"],
        "desc": "单意图→TutorAgent",
    },
    {
        "id": 22, "difficulty": 2,
        "message": "什么是随机森林，讲讲它的原理，说说它的优缺点，再出几道练习题",
        "expected_intents": ["tutor_question", "exercise_gen"],
        "expected_centers": {"auto", "exercise"},
        "tutor_keywords": ["随机森林", "决策树"],
        "tutor_optional": ["集成", "投票", "特征", "bagging", "bootstrap"],
        "desc": "答疑+出题双意图",
    },
    {
        "id": 23, "difficulty": 3,
        "message": "我想学强化学习但数学基础差，怎么规划？",
        "expected_intents": ["learning_path", "profile_building"],
        "expected_centers": {"plan", "auto"},
        "tutor_keywords": ["强化", "数学"],
        "tutor_optional": ["规划", "基础", "路线"],
        "desc": "学习规划+画像构建",
    },
    {
        "id": 24, "difficulty": 3,
        "message": "我刚入门 AI，学完了线性回归，下一步该学什么？为什么？",
        "expected_intents": ["tutor_question", "profile_building"],
        "expected_centers": {"auto"},
        "tutor_keywords": ["线性回归", "逻辑回归", "分类"],
        "tutor_optional": ["梯度下降", "过拟合", "正则化", "模型评估"],
        "desc": "画像提取+学习建议",
    },
]


# ── Scoring Engine ─────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id: int
    difficulty: int
    category: str  # "p0" | "p1" | "combined"
    message: str
    desc: str
    score: float = 0.0
    details: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    raw_output: str = ""


class ScoringEngine:
    """量化评分引擎：每例 100 分制，加权后算总分。"""

    @staticmethod
    def score_router(result: dict, case: dict) -> tuple[float, dict]:
        """P0 Router 评分: intent(50) + center(30) + multi(10) + params(10)"""
        details = {}
        tasks = result.get("tasks", [])
        actual_intents = [t.intent for t in tasks]
        actual_centers = {t.mode for t in tasks}
        actual_confidences = [t.confidence for t in tasks]

        expected_intents = case["expected_intents"]
        expected_centers = case["expected_centers"]

        # 1. Intent 匹配 (50%)
        intent_hits = sum(1 for ei in expected_intents if ei in actual_intents)
        if len(expected_intents) == 1:
            intent_score = 50.0 if expected_intents[0] in actual_intents else 0.0
        else:
            # 多意图：按命中率给分
            intent_score = (intent_hits / len(expected_intents)) * 50.0
        details["intent"] = round(intent_score, 1)

        # 2. Center 路由 (30%)
        center_hits = len(expected_centers & actual_centers)
        center_score = (center_hits / len(expected_centers)) * 30.0 if expected_centers else 30.0
        details["center"] = round(center_score, 1)

        # 3. 多意图排序 (10%)
        if len(actual_intents) > 1 and len(expected_intents) > 1:
            top_intent = actual_intents[0]
            top_confidence = actual_confidences[0] if actual_confidences else 0
            second_confidence = actual_confidences[1] if len(actual_confidences) > 1 else 0
            if top_intent in expected_intents and top_confidence >= second_confidence:
                multi_score = 10.0
            else:
                multi_score = 5.0
        else:
            multi_score = 10.0  # 单意图不扣分
        details["multi_order"] = round(multi_score, 1)

        # 4. 参数提取 (10%)
        params = tasks[0].params if tasks else {}
        params_score = 10.0
        if not params:
            params_score = 5.0
        elif isinstance(params, dict):
            topic = params.get("topic", "")
            question = params.get("question", "")
            if not topic and not question:
                params_score = 5.0
        details["params"] = round(params_score, 1)

        # mutex 专项加分: 验证互斥组正确排除
        if case.get("mutex_expected"):
            mutex_dropped = case.get("mutex_dropped", "")
            if mutex_dropped and mutex_dropped not in actual_intents:
                details["mutex"] = "OK"
            else:
                details["mutex"] = "FAIL"

        total = intent_score + center_score + multi_score + params_score
        return min(total, 100.0), details

    @staticmethod
    @staticmethod
    def score_tutor(response: str, state: dict, case: dict,
                    judge_result: dict | None = None) -> tuple[float, dict]:
        """P1 TutorAgent 评分: LLM-as-Judge 五维评分为主，关键词覆盖为兜底。

        当 judge_result 为 None 时（judge LLM 不可用），回退到关键词评分。
        """
        if judge_result and isinstance(judge_result, dict) and "total" in judge_result:
            # LLM-as-Judge 五维评分：每维 1-20 分
            # 直接使用 LLM 打出的 total（满分 100），不做二次加工
            return float(judge_result["total"]), {}
        # 回退：关键词覆盖评分
        return ScoringEngine._score_tutor_keywords(response, state, case)

    @staticmethod
    def _score_tutor_keywords(response: str, state: dict, case: dict) -> tuple[float, dict]:
        """关键词覆盖兜底评分（judge LLM 不可用时使用）"""
        details = {}
        text = response or ""
        text_lower = text.lower()

        required = case.get("required_keywords", [])
        optional = case.get("optional_keywords", [])
        forbidden = case.get("forbidden_patterns", [])

        required_hits = sum(1 for kw in required if kw.lower() in text_lower)
        keyword_score = (required_hits / len(required)) * 40.0 if required else 40.0
        optional_hits = sum(1 for kw in optional if kw.lower() in text_lower)
        optional_bonus = min(optional_hits / max(len(optional), 1), 1.0) * 5.0
        keyword_score = min(keyword_score + optional_bonus, 45.0)
        details["keyword_coverage"] = round(keyword_score, 1)

        structure_score = 0.0
        paragraphs = [p for p in text.split("\n") if p.strip()]
        if len(paragraphs) >= 3:
            structure_score += 8.0
        if re.search(r"\d+[\.\、\)）]", text) or re.search(r"[-•\*\–\—]", text):
            structure_score += 6.0
        first_sent = paragraphs[0][:80] if paragraphs else ""
        last_sent = paragraphs[-1][:80] if paragraphs else ""
        if len(first_sent) > 20:
            structure_score += 3.0
        if len(last_sent) > 30 and any(
            kw in last_sent for kw in ["综上", "总之", "总的来说", "因此", "所以", "希望"]
        ):
            structure_score += 3.0
        details["structure"] = round(min(structure_score, 20.0), 1)

        quality_score = 0.0
        text_len = len(text)
        if text_len >= 200:
            quality_score += 5.0
        elif text_len >= 100:
            quality_score += 3.0
        elif text_len >= 50:
            quality_score += 1.0
        if re.search(r"[一-鿿]", text):
            quality_score += 5.0
        concept_count = len(re.findall(r"[A-Z][a-zA-Z]+|[一-鿿]{2,6}", text))
        if concept_count >= 5:
            quality_score += 5.0
        elif concept_count >= 2:
            quality_score += 2.0
        details["quality"] = round(min(quality_score, 15.0), 1)

        domain = state.get("domain", "")
        is_ai = case.get("is_ai_domain", True)
        if is_ai:
            domain_score = 10.0 if domain == "ai" else (5.0 if not domain else 7.0)
        else:
            domain_score = 10.0 if domain == "general" else (5.0 if not domain else 7.0)
        details["domain_routing"] = round(domain_score, 1)

        safety_score = 15.0
        for pattern in forbidden:
            if re.search(pattern, text, re.IGNORECASE):
                safety_score -= 10.0
        details["safety"] = round(max(0.0, safety_score), 1)

        total = keyword_score + structure_score + quality_score + domain_score + safety_score
        return min(total, 100.0), details

    @staticmethod
    def score_combined(route_result: dict, tutor_response: str,
                       tutor_state: dict, case: dict,
                       judge_result: dict | None = None) -> tuple[float, dict]:
        """Combined 联合评分: routing(40) + response(40, LLM-as-Judge) + pipeline(20)"""
        details = {}

        # 1. 路由正确 (40%)
        tasks = route_result.get("tasks", [])
        actual_intents = [t.intent for t in tasks]
        actual_centers = {t.mode for t in tasks}
        expected_intents = case["expected_intents"]
        expected_centers = case["expected_centers"]

        intent_hits = sum(1 for ei in expected_intents if ei in actual_intents)
        intent_ratio = intent_hits / len(expected_intents) if expected_intents else 1.0
        center_hits = len(expected_centers & actual_centers)
        center_ratio = center_hits / len(expected_centers) if expected_centers else 1.0
        route_score = intent_ratio * 20.0 + center_ratio * 20.0
        details["routing"] = round(route_score, 1)

        # 2. Tutor 响应 (40%) — 用 LLM-as-Judge 或回退关键词评分
        tutor_score, _tutor_details = ScoringEngine.score_tutor(
            tutor_response, tutor_state, {
                "required_keywords": case.get("tutor_keywords", []),
                "optional_keywords": case.get("tutor_optional", []),
                "forbidden_patterns": [],
                "is_ai_domain": True,
            },
            judge_result=judge_result,
        )
        response_weighted = (tutor_score / 100.0) * 40.0
        details["response"] = round(response_weighted, 1)

        # 3. 管线完整性 (20%)
        pipeline_score = 0.0
        if tasks:
            pipeline_score += 10.0
        if tutor_response and len(tutor_response) > 20:
            pipeline_score += 10.0
        details["pipeline"] = round(pipeline_score, 1)

        total = route_score + response_weighted + pipeline_score
        return min(total, 100.0), details


# ── Test Runners ────────────────────────────────────────────────────────

async def run_p0_tests() -> list[CaseResult]:
    """P0 离线关键词路由：12 例"""
    from app.centers.router_agent import RouterAgent
    from app.services.intent_extractor import IntentExtractor

    router = RouterAgent(intent_extractor=IntentExtractor(use_mock=True))
    engine = ScoringEngine()
    results = []

    for case in P0_CASES:
        start = time.perf_counter()
        errors = []
        try:
            plan = await router.route(case["message"], mode="auto")
            route_result = {
                "tasks": plan.tasks,
                "is_clear": plan.is_clear,
                "meta": plan.intent_meta,
            }
        except Exception as e:
            route_result = {"tasks": [], "is_clear": False, "meta": {}}
            errors.append(str(e))

        score, details = engine.score_router(route_result, case)
        elapsed = (time.perf_counter() - start) * 1000
        details["elapsed_ms"] = round(elapsed, 1)

        actual_intents = [t.intent for t in route_result.get("tasks", [])]
        actual_centers = [t.mode for t in route_result.get("tasks", [])]

        results.append(CaseResult(
            case_id=case["id"],
            difficulty=case["difficulty"],
            category="p0",
            message=case["message"],
            desc=case["desc"],
            score=score,
            details={**details, "actual_intents": actual_intents,
                     "actual_centers": actual_centers},
            errors=errors,
        ))
    return results


async def run_p1_tests() -> list[CaseResult]:
    """P1 TutorAgent 真实 LLM 测试：8 例"""
    from app.agents.tutor_agent import TutorAgent

    engine = ScoringEngine()
    results = []

    # 检查 API key 是否可用
    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                   or os.getenv("DASHSCOPE_API_KEY_FLASH"))
    if not has_api:
        print("  [WARN] 未检测到 API Key，P1 测试将使用 mock LLM（评分会很低）")

    for case in P1_CASES:
        start = time.perf_counter()
        errors = []
        response = ""
        state = {}
        judge_result = None
        try:
            agent = TutorAgent(use_mock_llm=not has_api)
            state = await agent.run({
                "messages": [{"role": "user", "content": case["message"]}],
                "user_id": 1,
                "student_profile": {},
                "course_id": "AI101",
            })
            response = state.get("response", "")
        except Exception as e:
            errors.append(f"TutorAgent failed: {e}")

        # LLM-as-Judge 质量评估
        if response and not errors:
            judge_start = time.perf_counter()
            judge_result = await judge_quality(
                case["message"], case["difficulty"], response,
            )
            judge_elapsed = (time.perf_counter() - judge_start) * 1000

        score, details = engine.score_tutor(
            response, state, case, judge_result=judge_result,
        )
        elapsed = (time.perf_counter() - start) * 1000
        # 合并 judge 详情
        if judge_result:
            details.update(_judge_to_details(
                judge_result,
                judge_elapsed if 'judge_elapsed' in dir() else 0,
            ))
        details["elapsed_ms"] = round(elapsed, 1)
        details["judge_used"] = judge_result is not None

        results.append(CaseResult(
            case_id=case["id"],
            difficulty=case["difficulty"],
            category="p1",
            message=case["message"],
            desc=case["desc"],
            score=score,
            details=details,
            errors=errors,
            raw_output=response[:500],
        ))
    return results


async def run_combined_tests() -> list[CaseResult]:
    """Combined 联合管线测试：4 例"""
    from app.centers.router_agent import RouterAgent
    from app.services.intent_extractor import IntentExtractor
    from app.agents.tutor_agent import TutorAgent

    router = RouterAgent(intent_extractor=IntentExtractor(use_mock=True))
    engine = ScoringEngine()
    results = []

    has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
                   or os.getenv("DASHSCOPE_API_KEY_FLASH"))

    for case in COMBINED_CASES:
        start = time.perf_counter()
        errors = []
        route_result = {}
        tutor_response = ""
        tutor_state = {}

        try:
            # Step 1: 路由
            plan = await router.route(case["message"], mode="auto")
            route_result = {"tasks": plan.tasks, "meta": plan.intent_meta}

            # Step 2: 对 auto 类 intent 执行 TutorAgent
            auto_tasks = [t for t in plan.tasks if t.mode == "auto"
                          and t.intent in ("tutor_question", "profile_building")]
            if auto_tasks:
                agent = TutorAgent(use_mock_llm=not has_api)
                tutor_state = await agent.run({
                    "messages": [{"role": "user", "content": case["message"]}],
                    "user_id": 1,
                    "student_profile": {},
                    "course_id": "AI101",
                })
                tutor_response = tutor_state.get("response", "")
        except Exception as e:
            errors.append(str(e))

        # LLM-as-Judge 质量评估
        judge_result = None
        if tutor_response and not errors:
            judge_result = await judge_quality(
                case["message"], case["difficulty"], tutor_response,
            )

        score, details = engine.score_combined(
            route_result, tutor_response, tutor_state, case,
            judge_result=judge_result,
        )
        elapsed = (time.perf_counter() - start) * 1000
        # 合并 judge 详情
        if judge_result:
            details.update(_judge_to_details(judge_result, 0))
        details["elapsed_ms"] = round(elapsed, 1)
        details["judge_used"] = judge_result is not None

        results.append(CaseResult(
            case_id=case["id"],
            difficulty=case["difficulty"],
            category="combined",
            message=case["message"],
            desc=case["desc"],
            score=score,
            details=details,
            errors=errors,
            raw_output=tutor_response[:300],
        ))
    return results


# ── Report ──────────────────────────────────────────────────────────────

DIFFICULTY_LABELS = {1: "★☆☆", 2: "★★☆", 3: "★★★"}


def print_report(p0_results, p1_results, combined_results):
    all_results = p0_results + p1_results + combined_results

    print()
    print("=" * 95)
    print("  P0+P1 联合测试：24 例梯度暴力测试 — 结果报告")
    print("=" * 95)

    # ── 逐例明细 ──
    for r in all_results:
        diff_label = DIFFICULTY_LABELS.get(r.difficulty, "???")
        cat_label = {"p0": "P0", "p1": "P1", "combined": "CB"}[r.category]
        status = "[PASS]" if r.score >= 70 else "[FAIL]"
        msg_short = r.message[:50] + "..." if len(r.message) > 50 else r.message

        print(f"\n  ┌─ [{r.case_id:2d}] {cat_label} {diff_label} {status} "
              f"({r.score:.1f}/100)")
        print(f"  │ 输入: {msg_short}")
        print(f"  │ 说明: {r.desc}")

        if r.errors:
            for e in r.errors:
                print(f"  │ ❌ 错误: {e}")

        print(f"  │ 评分明细: {r.details}")

        if r.raw_output:
            output_preview = r.raw_output[:200].replace("\n", "\\n")
            print(f"  │ LLM输出: {output_preview}...")

    # ── 汇总统计 ──
    print()
    print("=" * 95)
    print("  汇总统计")
    print("=" * 95)

    def category_stats(results, label):
        if not results:
            print(f"  {label}: (无结果)")
            return 0.0, 0, 0
        avg = sum(r.score for r in results) / len(results)
        passed = sum(1 for r in results if r.score >= 70)
        failed = len(results) - passed
        status = "[PASS]" if avg >= 70 else "[FAIL]"
        print(f"  {label:25s} 平均分: {avg:5.1f}  {status}  "
              f"(通过: {passed}/{len(results)}, 失败: {failed}/{len(results)})")
        return avg, passed, failed

    p0_avg, p0_pass, p0_fail = category_stats(p0_results, "P0 Router (12 例)")
    p1_avg, p1_pass, p1_fail = category_stats(p1_results, "P1 TutorAgent (8 例)")
    cb_avg, cb_pass, cb_fail = category_stats(combined_results, "联合管线 (4 例)")

    # 加权总分
    weighted_total = p0_avg * 0.40 + p1_avg * 0.35 + cb_avg * 0.25
    grand_pass = (weighted_total > 90
                  and p0_avg >= 70 and p1_avg >= 70 and cb_avg >= 70)

    print(f"  {'─' * 55}")
    print(f"  加权总分 (P0×0.40 + P1×0.35 + Combined×0.25): "
          f"{weighted_total:.1f}")
    print(f"  判定: {'[PASS] ✓ 准确率 > 90%' if grand_pass else '[FAIL] ✗'}")

    # 按难度统计
    print()
    print("  按难度分层:")
    for diff in [1, 2, 3]:
        diff_results = [r for r in all_results if r.difficulty == diff]
        if diff_results:
            avg = sum(r.score for r in diff_results) / len(diff_results)
            passed = sum(1 for r in diff_results if r.score >= 70)
            label = DIFFICULTY_LABELS[diff]
            print(f"    {label} ({len(diff_results)}例)  平均: {avg:.1f}  "
                  f"通过: {passed}/{len(diff_results)}")

    print()
    print("=" * 95)

    return grand_pass


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    print("=" * 95)
    print("  P0+P1 联合测试：24 例梯度暴力测试")
    print("=" * 95)

    # ── P0 ──
    print("\n  [1/3] P0 Router 离线测试 (12 例)...")
    p0_results = await run_p0_tests()
    for r in p0_results:
        marker = "✓" if r.score >= 70 else "✗"
        print(f"    [{r.case_id:2d}] {marker} {r.score:.1f}/100  "
              f"{r.desc[:45]}")

    # ── P1 ──
    print("\n  [2/3] P1 TutorAgent LLM 测试 (8 例) [LLM-as-Judge]...")
    p1_results = await run_p1_tests()
    for r in p1_results:
        marker = "✓" if r.score >= 70 else "✗"
        judge_info = ""
        if r.details.get("judge_used"):
            j = r.details
            judge_info = (f"A{j.get('judge_accuracy',0)} D{j.get('judge_depth',0)} "
                         f"H{j.get('judge_helpfulness',0)} S{j.get('judge_structure',0)} "
                         f"F{j.get('judge_domain_fit',0)}")
        else:
            judge_info = "(关键词评分)"
        print(f"    [{r.case_id:2d}] {marker} {r.score:.1f}/100  "
              f"{judge_info}  {r.desc[:35]}")

    # ── Combined ──
    print("\n  [3/3] Combined 联合管线测试 (4 例)...")
    combined_results = await run_combined_tests()
    for r in combined_results:
        marker = "✓" if r.score >= 70 else "✗"
        print(f"    [{r.case_id:2d}] {marker} {r.score:.1f}/100  "
              f"{r.desc[:45]}")

    # ── Report ──
    grand_pass = print_report(p0_results, p1_results, combined_results)

    return 0 if grand_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
