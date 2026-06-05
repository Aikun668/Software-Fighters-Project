"""FlashCardAgent — 闪卡生成智能体

从 ContentAgent 产出的 content_blocks 中自动提取核心概念，
生成问答对闪卡，支持"学习→记忆→测验"闭环。
"""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.orchestration.agent_turn_summary import AgentTurnSummary
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

MAX_CARDS = 10


class Card(TypedDict, total=False):
    front: str
    back: str


class FlashCardState(TypedDict, total=False):
    topic: str
    content_blocks: list[dict]
    key_concepts: list[str]
    cards: list[Card]
    content_summary: str
    blocks: list[dict]
    response: str


class FlashCardAgent(BaseAgent):
    """闪卡生成 Agent — 输出 flash_cards block"""

    def __init__(self, config=None, use_mock_llm: bool = False,
                 model_profile=None):
        super().__init__(
            agent_name="flashcard_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
            model_profile=model_profile,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(FlashCardState)
        graph.add_node("extract", self._extract_node)
        graph.add_node("generate", self._generate_node)
        graph.set_entry_point("extract")
        graph.add_edge("extract", "generate")
        graph.set_finish_point("generate")
        return graph.compile()

    async def _extract_node(self, state: FlashCardState) -> dict:
        """从 content_blocks 提取关键概念和内容摘要"""
        topic = state.get("topic", "")
        content_blocks = state.get("content_blocks", [])

        if not content_blocks:
            return {
                "key_concepts": [],
                "content_summary": f"关于{topic}的知识内容",
            }

        concepts = []
        summaries = []

        for block in content_blocks[:10]:
            heading = block.get("heading", "")
            content = block.get("content", "")
            block_type = block.get("type", "")

            if heading:
                concepts.append(str(heading))
            if content and block_type not in ("mindmap", "mermaid"):
                text = str(content)
                if len(text) > 200:
                    text = text[:200] + "..."
                summaries.append(text)

        key_concepts = concepts[:8]
        content_summary = "\n".join(summaries[:5]) if summaries else f"关于{topic}的知识内容"

        return {
            "key_concepts": key_concepts,
            "content_summary": content_summary,
        }

    async def _generate_node(self, state: FlashCardState) -> dict:
        """调用 LLM 生成闪卡问答对"""
        topic = state.get("topic", "")
        key_concepts = state.get("key_concepts", [])
        content_summary = state.get("content_summary", "")

        if not key_concepts:
            logger.info(f"No key concepts for '{topic}', returning empty flashcards")
            return self._build_output([])

        sys_prompt = self._load_extra_prompt("system.yaml", key="system")
        user_tpl = self._load_extra_prompt("system.yaml", key="user_template")
        user_prompt = interpolate_variables(
            user_tpl,
            {
                "topic": topic,
                "content_summary": content_summary,
                "key_concepts": "、".join(key_concepts),
                "student_profile": "（暂无学生画像，按默认难度生成）",
            },
        )

        try:
            result = await self._call_llm_json(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                expected_key="cards",
                fallback={},
                validator=self._validate_cards,
            )
            cards = result.get("cards", [])

            if not cards:
                cards = self._build_fallback_cards(topic, key_concepts)
        except Exception as e:
            logger.error(f"FlashCardAgent LLM call failed unexpectedly: {e}")
            cards = self._build_fallback_cards(topic, key_concepts)

        cards = self._sanitize_cards(cards)

        logger.info(f"FlashCardAgent generated {len(cards)} cards for topic '{topic}'")
        return self._build_output(cards)

    @staticmethod
    def _validate_cards(result: dict) -> list[str]:
        """验证 cards 字段的结构完整性"""
        issues = []
        cards = result.get("cards", [])
        if not isinstance(cards, list):
            issues.append("cards 必须是数组")
            return issues
        if len(cards) == 0:
            issues.append("cards 不能为空数组")
            return issues
        for i, card in enumerate(cards):
            if not isinstance(card, dict):
                issues.append(f"cards[{i}] 必须是对象")
                continue
            if not isinstance(card.get("front"), str) or not card["front"]:
                issues.append(f"cards[{i}] 缺少或 front 为空")
            if not isinstance(card.get("back"), str) or not card["back"]:
                issues.append(f"cards[{i}] 缺少或 back 为空")
        return issues

    def _build_fallback_cards(self, topic: str, key_concepts: list[str]) -> list[dict]:
        """从关键概念静态构建闪卡（fallback 路径）"""
        cards = []
        for concept in key_concepts[:MAX_CARDS]:
            cards.append({
                "front": f"什么是 {concept}？",
                "back": f"{concept} 是 {topic} 中的一个重要概念。",
            })
        return cards

    @staticmethod
    def _sanitize_cards(cards: list[dict]) -> list[dict]:
        """清理并限制卡片数量"""
        sanitized = []
        for card in cards[:MAX_CARDS]:
            if not isinstance(card, dict):
                continue
            front = str(card.get("front", "")).strip()
            back = str(card.get("back", "")).strip()
            if front and back:
                sanitized.append({"front": front, "back": back})
        return sanitized

    def _build_output(self, cards: list[dict]) -> dict:
        """构建标准输出格式"""
        return {
            "blocks": [{
                "type": "flash_cards",
                "heading": "核心概念速记",
                "content": {"cards": cards},
            }],
            "response": f"已生成 {len(cards)} 张记忆闪卡",
        }

    def create_turn_summary(
        self, state: dict, output: dict
    ) -> AgentTurnSummary:
        """Override: 提取闪卡数量作为 metrics"""
        topic = state.get("topic", "")
        cards = []

        blocks = output.get("blocks", [])
        for block in blocks:
            if block.get("type") == "flash_cards":
                content = block.get("content", {})
                cards = content.get("cards", [])
                break

        concepts = []
        for card in cards[:8]:
            front = card.get("front", "")
            if front:
                concepts.append(str(front))

        return AgentTurnSummary(
            agent_name=self.__class__.__name__,
            topic=topic,
            covered_concepts=concepts,
            generation_intent=f"为{topic}生成 {len(cards)} 张记忆闪卡",
            avoid_duplicating=list(concepts[:4]),
            output_metrics={"card_count": len(cards)},
        )