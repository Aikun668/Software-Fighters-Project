"""领域分类器 — 多信号融合判断用户当前对话领域，决定 KB 注入策略。

信号优先级: course_id > KB cosine distance > 关键词匹配

【决策所有权】内容领域分类（AI / 通用）—— 本模块是唯一拥有者。
  - 唯一调用点：`TutorAgent._respond_node`（`app/agents/tutor_agent.py`）
  - 输出：`"ai"` / `"general"`，仅影响 KB 注入、类比与 system prompt 选择
  - 禁止：参与 Center / Agent 选择（**分类 ≠ 路由**）
  - 约定：`archive/temp_file/9.15工程改造计划/0、产品方向与约束/三类决策与命名约定.md`

【命名澄清】本类原名 `DomainRouter`（**P3-B2 已改名** `DomainClassifier`；模块同步由
  `domain_router.py` 改为 `domain_classifier.py`）。它**不路由任何请求**，实为内容二分类器；
  与 `CapabilityGate`（一级请求分发）、`RouterAgent`（二级意图分发）职责不同，**不可互换**。
"""

import logging

logger = logging.getLogger(__name__)

AI_THRESHOLD = 0.5          # ChromaDB cosine distance: < 0.5 视为与 KB 相关
AI_COLLECTIONS = {"ai_intro", "ml_basics", "dl_advanced"}

AI_KEYWORDS = frozenset({
    "机器学习", "深度学习", "神经网络", "卷积", "梯度下降", "反向传播",
    "损失函数", "激活函数", "过拟合", "正则化", "强化学习", "监督学习",
    "无监督学习", "Transformer", "注意力机制", "自然语言处理", "计算机视觉",
    "生成对抗网络", "GAN", "RNN", "LSTM", "CNN", "NLP", "CV",
    "AI", "人工智能", "大模型", "LLM", "决策树", "随机森林", "聚类",
})


class DomainClassifier:
    """多信号融合领域分类器，纯规则，零延迟。"""

    AI_THRESHOLD = AI_THRESHOLD
    AI_COLLECTIONS = AI_COLLECTIONS

    @staticmethod
    def classify(
        query: str,
        course_id: str = "",
        kb_top_score: float | None = None,
    ) -> str:
        """判断用户当前对话领域。

        Args:
            query: 用户消息原文
            course_id: Java 传来的课程 ID（最权威信号）
            kb_top_score: KB 向量检索 top-1 的 cosine distance

        Returns:
            "ai" — 走 AI 专用管线（注入 KB + 类比 + AI prompt）
            "general" — 走通用管线（LLM 自身知识回答）
        """
        # 信号 1: course_id 直接指示（最权威）
        if course_id and course_id in AI_COLLECTIONS:
            logger.debug(f"Domain=ai by course_id={course_id}")
            return "ai"

        # 信号 2: KB 向量相似度 — top-1 都不像 AI 内容，说明不在 AI 领域
        if kb_top_score is not None and kb_top_score > AI_THRESHOLD:
            logger.debug(f"Domain=general by kb_top_score={kb_top_score:.3f}")
            return "general"

        # 信号 3: 关键词快速判断
        if _has_ai_keywords(query):
            logger.debug("Domain=ai by keyword match")
            return "ai"

        return "general"

    @staticmethod
    def should_inject_kb(kb_top_score: float | None) -> bool:
        """KB 内容是否与当前问题足够相关，值得注入。"""
        if kb_top_score is None:
            return False
        return kb_top_score < AI_THRESHOLD

    @staticmethod
    def should_inject_analogy(domain: str) -> bool:
        """类比库只在 AI 领域触发。"""
        return domain == "ai"


def get_domain_classifier() -> DomainClassifier:
    return DomainClassifier()


def _has_ai_keywords(query: str) -> bool:
    """快速关键词命中检测，O(n) 子串匹配。"""
    q = query.lower()
    return any(kw.lower() in q for kw in AI_KEYWORDS)
