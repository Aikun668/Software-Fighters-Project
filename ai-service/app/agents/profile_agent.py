"""
ProfileAgent — 对话式学习画像构建智能体

借鉴 DeepTutor L3 profile 更新机制 + OpenMAIC LangGraph 拓扑
3 节点 StateGraph：extract → merge → response

extract_node: LLM 从最新消息中抽取画像片段（借鉴 DeepTutor update_l3.yaml）
merge_node:  纯逻辑：新片段与 DB 已有画像增量合并
response_node: LLM 基于当前画像生成个性化回复
"""

import json
import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph
from sqlalchemy import select

from app.agents.base_agent import BaseAgent
from app.db.database import get_db
from app.models.profile import StudentProfile
from app.services.llm_service import create_llm
from app.utils.prompt_loader import interpolate_variables

logger = logging.getLogger(__name__)

DIMENSIONS = [
    "knowledge_base",
    "cognitive_style",
    "learning_goal",
    "weak_points",
    "learning_pace",
    "interest_direction",
]

ARRAY_DIMENSIONS = {"weak_points", "interest_direction"}
NUMBER_DIMENSIONS = {"knowledge_base"}
REPLACE_DIMENSIONS = {"cognitive_style", "learning_goal", "learning_pace"}

# 动态权重参数
TAG_EMA_ALPHA = 0.4       # 标签权重 EMA 系数（每次出现向 1.0 收敛）
TAG_CUTOFF = 0.2          # 低于此权重自动清除
STABILITY_N = 3           # REPLACE 维度连续确认次数阈值

MAX_EXTRACT_TURNS = 10


class ProfileState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    current_profile: dict
    extracted_fragment: dict
    profile_changed: bool
    response: str


class ProfileAgent(BaseAgent):
    """对话式学习画像构建智能体"""

    def __init__(self, config=None, use_mock_llm: bool = True):
        # init base with system.yaml as default prompt
        super().__init__(
            agent_name="profile_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm

        # 加载 extract prompt 模板（system + user 两部分）
        self.extract_system_template = self._load_prompt(
            filename="extract.yaml", key="system"
        )
        self.extract_user_template = self._load_prompt(
            filename="extract.yaml", key="user"
        )

        # 创建 extract 专用 LLM（temperature=0.3 保证结构化输出一致性）
        # system_prompt 在每次调用 chat() 时动态传入
        self.extract_llm = create_llm(
            temperature=0.3,
            use_mock=use_mock_llm,
        )

        # response 专用 LLM 已在 BaseAgent.__init__ 中创建（self.llm）
        # 覆盖 temperature 为 0.7 保证对话自然
        self.response_llm = create_llm(
            temperature=0.7,
            use_mock=use_mock_llm,
        )

    def build_graph(self) -> "CompiledStateGraph":
        graph = StateGraph(ProfileState)

        graph.add_node("extract", self._extract_node)
        graph.add_node("merge", self._merge_node)
        graph.add_node("response", self._response_node)

        graph.set_entry_point("extract")
        graph.add_edge("extract", "merge")
        graph.add_edge("merge", "response")
        graph.set_finish_point("response")

        return graph.compile()

    async def _extract_node(self, state: ProfileState) -> dict:
        """LLM 从最新一轮对话中抽取画像片段"""
        messages = state.get("messages", [])
        current_profile = state.get("current_profile", {})

        # 注入已有画像 + 本轮对话到 user 模板
        existing_json = json.dumps(current_profile, ensure_ascii=False)
        current_turn = self._format_current_turn(messages)

        extract_user_prompt = interpolate_variables(
            self.extract_user_template,
            {
                "existing_profile": existing_json,
                "current_turn": current_turn,
            },
        )

        # system prompt = 角色定义 + 规则；user prompt = 具体数据
        # 截断历史消息，防止超出 token 限制
        recent_messages = messages[-MAX_EXTRACT_TURNS:] if len(messages) > MAX_EXTRACT_TURNS else messages
        extract_messages = list(recent_messages) + [
            {"role": "user", "content": extract_user_prompt}
        ]

        try:
            result_text = await self.extract_llm.chat(
                extract_messages,
                system_prompt=self.extract_system_template,
            )
            fragment = self._parse_extract_result(result_text)
        except (RuntimeError, ConnectionError) as e:
            logger.error(f"Extract LLM failed: {e}, using empty fragment")
            fragment = {}

        return {"extracted_fragment": fragment}

    async def _merge_node(self, state: ProfileState) -> dict:
        """纯逻辑：新片段与 DB 已有画像合并"""
        user_id = state.get("user_id", 1)
        fragment = state.get("extracted_fragment", {})

        if not fragment:
            return {
                "current_profile": state.get("current_profile", {}),
                "profile_changed": False,
            }

        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(
                        StudentProfile.user_id == user_id
                    )
                )
                profile = result.scalar_one_or_none()

                if profile is None:
                    profile = StudentProfile(user_id=user_id)
                    session.add(profile)

                changed = self._apply_merge(profile, fragment)

                if changed:
                    profile.raw_profile_json = {
                        d: getattr(profile, d) for d in DIMENSIONS
                    }
                    profile.raw_profile_json["tag_weights"] = profile.tag_weights
                    profile.raw_profile_json["stability_counter"] = (
                        profile.stability_counter
                    )

                await session.commit()

                current_profile = {
                    d: getattr(profile, d) for d in DIMENSIONS
                }
                current_profile["tag_weights"] = profile.tag_weights
                current_profile["stability_counter"] = profile.stability_counter
                return {
                    "current_profile": current_profile,
                    "profile_changed": changed,
                }
        except Exception as e:
            logger.warning(f"DB merge failed: {e}, using in-memory merge")
            # 降级：纯内存合并
            old = state.get("current_profile", {})
            merged, changed = self._merge_in_memory(old, fragment)
            return {
                "current_profile": merged,
                "profile_changed": changed,
            }

    async def _response_node(self, state: ProfileState) -> dict:
        """LLM 基于当前画像生成个性化回复"""
        messages = state.get("messages", [])
        current_profile = state.get("current_profile", {})

        # 注入当前画像到 response prompt
        profile_text = self._format_profile_for_response(current_profile)
        system_with_profile = interpolate_variables(
            self.system_prompt, {"current_profile": profile_text}
        )

        try:
            full_response = ""
            async for chunk in self.response_llm.chat_stream(
                messages, system_prompt=system_with_profile
            ):
                full_response += chunk
        except (ConnectionError, RuntimeError) as e:
            logger.error(f"Response LLM failed: {e}")
            full_response = "好的，我正在了解你的学习情况，请继续说～"

        return {"response": full_response}

    # ── helper methods ────────────────────────────────────────────

    def _format_current_turn(self, messages: list[dict]) -> str:
        """格式化最近一轮对话为文本"""
        recent = messages[-4:] if len(messages) > 4 else messages
        lines = []
        for m in recent:
            role = "学生" if m["role"] == "user" else "AI"
            lines.append(f"[{role}]: {m['content']}")
        return "\n".join(lines)

    def _format_profile_for_response(self, profile: dict) -> str:
        """将画像 dict 格式化为 LLM 可读的文本（含标签权重）"""
        if not profile or all(v is None or v == [] for v in profile.values()):
            return "（尚无画像信息，这是第一次对话）"

        lines = ["当前学生画像："]
        labels = {
            "knowledge_base": "知识基础",
            "cognitive_style": "学习风格",
            "learning_goal": "学习目标",
            "weak_points": "薄弱环节",
            "learning_pace": "学习节奏",
            "interest_direction": "兴趣方向",
        }
        tag_weights = profile.get("tag_weights", {})

        for dim, label in labels.items():
            val = profile.get(dim)
            if val is not None and val != []:
                if isinstance(val, list):
                    # 附加权重信息
                    weights = tag_weights.get(dim, {})
                    parts = [
                        f"{tag}({weights[tag]:.0%})" if tag in weights else tag
                        for tag in val[:6]  # 最多展示 6 个标签
                    ]
                    val = "、".join(parts)
                elif dim == "knowledge_base":
                    val = f"{val}/100"
                lines.append(f"  - {label}: {val}")

        return "\n".join(lines)

    def _parse_extract_result(self, text: str) -> dict:
        """解析 LLM 输出的 JSON，使用 parse_llm_json 三层解析"""
        from app.utils.json_parser import parse_llm_json

        data = parse_llm_json(text, fallback={})
        if not isinstance(data, dict):
            data = {}
        updates = data.get("updates", data)
        return {k: v for k, v in updates.items() if k in DIMENSIONS}

    def _apply_merge(self, profile: StudentProfile, fragment: dict) -> bool:
        """将 fragment 合并到 ORM 对象（动态权重 + 稳定性门控），返回是否发生变化"""
        changed = False

        tag_weights = dict(profile.tag_weights or {})
        stability = dict(profile.stability_counter or {})

        for dim, new_val in fragment.items():
            if new_val is None or new_val == []:
                continue

            if dim in ARRAY_DIMENSIONS:
                dim_weights = dict(tag_weights.get(dim, {}))
                new_tags = set(new_val)
                existing_tags = set(dim_weights.keys())

                # 未被本轮提取的标签 → 衰减
                for tag in existing_tags - new_tags:
                    decayed = round(dim_weights[tag] * (1 - TAG_EMA_ALPHA), 2)
                    if decayed >= TAG_CUTOFF:
                        dim_weights[tag] = decayed
                    else:
                        del dim_weights[tag]

                # 本轮出现的标签 → EMA 增强（目标值 1.0）
                for tag in new_tags:
                    old_w = dim_weights.get(tag, 0.0)
                    dim_weights[tag] = round(
                        old_w * (1 - TAG_EMA_ALPHA) + TAG_EMA_ALPHA, 2
                    )

                if dim_weights != tag_weights.get(dim, {}):
                    tag_weights[dim] = dim_weights
                    changed = True

                # 向后兼容：同步到旧版 list 字段（按权重降序）
                legacy = sorted(
                    dim_weights.keys(), key=lambda k: dim_weights[k], reverse=True
                )
                if legacy != getattr(profile, dim):
                    setattr(profile, dim, legacy)
                    changed = True

            elif dim in NUMBER_DIMENSIONS:
                try:
                    new_num = float(new_val)
                except (TypeError, ValueError):
                    logger.warning(f"Non-numeric value for {dim}: {new_val!r}")
                    continue
                old_val = getattr(profile, dim)
                if old_val is not None:
                    merged = int(old_val * 0.7 + new_num * 0.3)
                else:
                    merged = int(new_num)
                if merged != old_val:
                    setattr(profile, dim, merged)
                    changed = True

            elif dim in REPLACE_DIMENSIONS:
                sc = dict(stability.get(dim, {"value": None, "count": 0}))
                if sc["value"] == new_val:
                    sc["count"] += 1
                else:
                    sc = {"value": new_val, "count": 1}

                stability[dim] = sc

                if sc["count"] >= STABILITY_N and new_val != getattr(profile, dim):
                    setattr(profile, dim, new_val)
                    changed = True
                    stability[dim] = {"value": new_val, "count": 0}

        if tag_weights != (profile.tag_weights or {}):
            profile.tag_weights = tag_weights
            changed = True
        if stability != (profile.stability_counter or {}):
            profile.stability_counter = stability
            changed = True

        return changed

    def _merge_in_memory(
        self, old: dict, fragment: dict
    ) -> tuple[dict, bool]:
        """纯内存合并（DB 不可用时的降级方案，含动态权重）"""
        merged = dict(old)
        changed = False

        tag_weights = dict(old.get("tag_weights", {}))
        inmem_stability = dict(old.get("stability_counter", {}))

        for dim, new_val in fragment.items():
            if new_val is None or new_val == []:
                continue

            if dim in ARRAY_DIMENSIONS:
                dim_weights = dict(tag_weights.get(dim, {}))
                new_tags = set(new_val)
                existing_tags = set(dim_weights.keys())

                for tag in existing_tags - new_tags:
                    decayed = round(dim_weights[tag] * (1 - TAG_EMA_ALPHA), 2)
                    if decayed >= TAG_CUTOFF:
                        dim_weights[tag] = decayed
                    else:
                        del dim_weights[tag]

                for tag in new_tags:
                    old_w = dim_weights.get(tag, 0.0)
                    dim_weights[tag] = round(
                        old_w * (1 - TAG_EMA_ALPHA) + TAG_EMA_ALPHA, 2
                    )

                if dim_weights != tag_weights.get(dim, {}):
                    tag_weights[dim] = dim_weights
                    changed = True

                legacy = sorted(
                    dim_weights.keys(), key=lambda k: dim_weights[k], reverse=True
                )
                if legacy != merged.get(dim):
                    merged[dim] = legacy
                    changed = True

            elif dim in NUMBER_DIMENSIONS:
                try:
                    new_num = float(new_val)
                except (TypeError, ValueError):
                    logger.warning(f"Non-numeric value for {dim}: {new_val!r}")
                    continue
                old_val = merged.get(dim)
                if old_val is not None:
                    merged[dim] = int(old_val * 0.7 + new_num * 0.3)
                else:
                    merged[dim] = int(new_num)
                if merged[dim] != old_val:
                    changed = True

            elif dim in REPLACE_DIMENSIONS:
                sc = dict(inmem_stability.get(dim, {"value": None, "count": 0}))
                if sc["value"] == new_val:
                    sc["count"] += 1
                else:
                    sc = {"value": new_val, "count": 1}

                inmem_stability[dim] = sc

                if sc["count"] >= STABILITY_N and new_val != merged.get(dim):
                    merged[dim] = new_val
                    changed = True
                    inmem_stability[dim] = {"value": new_val, "count": 0}

        if tag_weights != old.get("tag_weights", {}):
            merged["tag_weights"] = tag_weights
        if inmem_stability != old.get("stability_counter", {}):
            merged["stability_counter"] = inmem_stability

        return merged, changed
