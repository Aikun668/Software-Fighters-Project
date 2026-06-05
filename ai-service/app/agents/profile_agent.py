"""
ProfileAgent — 对话式学习画像构建智能体

借鉴 DeepTutor L3 profile 更新机制：
  - 增量提取：只处理上次提取后的新消息，不重复处理旧消息
  - 条目模型：ARRAY 维度存储完整句子条目 + 置信度，而非孤立标签
  - 周期性审计：LLM 审视已有条目是否仍成立
  - 硬上限裁剪：每维度最多 N 个条目

5 节点 StateGraph：extract → merge → audit → response
"""

import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, StateGraph
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

# ── 条目系统常量 ──
MAX_ENTRIES_PER_DIM = 8        # 每维度最多条目数
MIN_CONFIDENCE_FOR_ACTIVE = 2  # 置信度 ≥2 才能标记为 active
AUDIT_INTERVAL = 10            # 每 N 轮对话触发一次审计
DEDUP_SIMILARITY = 0.55        # bigram 包含相似度阈值（中文短句匹配）

# 旧权重常量（NUMBER/REPLACE 维度仍使用）
TAG_EMA_ALPHA = 0.4
TAG_CUTOFF = 0.2
STABILITY_N = 3

MAX_EXTRACT_TURNS = 10


def _bigram_jaccard(a: str, b: str) -> float:
    """字符 bigram 包含相似度，对长度差异不敏感。

    使用交集 / min(|A|, |B|) 而非标准 Jaccard（交集 / 并集），
    使得"短句完全包含在长句中"得到 1.0 的相似度。
    """
    def bigrams(s: str) -> set[str]:
        s = s.replace(" ", "")
        if len(s) < 2:
            return {s}
        return {s[i:i + 2] for i in range(len(s) - 1)}
    ba = bigrams(a)
    bb = bigrams(b)
    if not ba or not bb:
        return 0.0
    intersection = len(ba & bb)
    denominator = min(len(ba), len(bb))
    return intersection / denominator if denominator > 0 else 0.0


class ProfileState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    current_profile: dict
    extracted_fragment: dict
    profile_changed: bool
    response: str
    # 增量提取上下文
    last_extracted_msg_index: int


class ProfileAgent(BaseAgent):
    """对话式学习画像构建智能体"""

    def __init__(self, config=None, use_mock_llm: bool = False):
        super().__init__(
            agent_name="profile_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm

        self.extract_system_template = self._load_prompt(
            filename="extract.yaml", key="system"
        )
        self.extract_user_template = self._load_prompt(
            filename="extract.yaml", key="user"
        )

        self.extract_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)
        self.response_llm = create_llm(temperature=0.7, use_mock=use_mock_llm)

        # 审计 LLM（temperature 更低，保证判断一致性）
        self.audit_llm = create_llm(temperature=0.2, use_mock=use_mock_llm)

    # ── graph ───────────────────────────────────────────────────────

    def build_graph(self):
        graph = StateGraph(ProfileState)

        graph.add_node("extract", self._extract_node)
        graph.add_node("merge", self._merge_node)
        graph.add_node("audit", self._audit_node)
        graph.add_node("response", self._response_node)

        graph.set_entry_point("extract")
        graph.add_edge("extract", "merge")
        graph.add_edge("merge", "audit")
        graph.add_edge("audit", "response")
        graph.set_finish_point("response")

        return graph.compile()

    # ── extract ─────────────────────────────────────────────────────

    async def _extract_node(self, state: ProfileState) -> dict:
        """增量提取：只处理上次提取后的新消息"""
        messages = state.get("messages", [])
        user_id = state.get("user_id", 1)
        last_idx = state.get("last_extracted_msg_index")

        # 如果 state 中没有增量索引，从 DB 加载
        if last_idx is None:
            last_idx = await self._load_last_extracted_index(user_id)

        # 计算新消息范围
        new_start = min(last_idx, len(messages))
        new_messages = messages[new_start:]

        if not new_messages:
            return {"extracted_fragment": {}, "last_extracted_msg_index": last_idx}

        # 限制一次最多处理 MAX_EXTRACT_TURNS 条新消息
        if len(new_messages) > MAX_EXTRACT_TURNS:
            new_messages = new_messages[-MAX_EXTRACT_TURNS:]
            new_start = len(messages) - len(new_messages)

        current_profile = state.get("current_profile", {})
        entries = current_profile.get("entries", {})
        entries_summary = self._format_entries_for_extract(entries)

        new_messages_text = self._format_new_messages(new_messages)
        extract_user_prompt = interpolate_variables(
            self.extract_user_template,
            {
                "existing_entries": entries_summary,
                "new_messages": new_messages_text,
            },
        )

        extract_messages = [
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

        # 更新已处理的消息索引
        new_last_idx = new_start + len(new_messages)

        return {
            "extracted_fragment": fragment,
            "last_extracted_msg_index": new_last_idx,
        }

    # ── merge ────────────────────────────────────────────────────────

    async def _merge_node(self, state: ProfileState) -> dict:
        """纯逻辑合并：条目模型（ARRAY 维度）+ EMA/稳定性（NUMBER/REPLACE）"""
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

                # 增量索引持久化
                new_last_idx = state.get("last_extracted_msg_index", 0)
                if new_last_idx > (profile.last_extracted_msg_index or 0):
                    profile.last_extracted_msg_index = new_last_idx

                changed = self._apply_merge(profile, fragment)

                if changed:
                    profile.raw_profile_json = {
                        d: getattr(profile, d) for d in DIMENSIONS
                    }
                    profile.raw_profile_json["entries"] = profile.entries
                    profile.raw_profile_json["tag_weights"] = profile.tag_weights
                    profile.raw_profile_json["stability_counter"] = (
                        profile.stability_counter
                    )

                # 递增审计计数器
                profile.audit_counter = (profile.audit_counter or 0) + 1

                await session.commit()

                current_profile = {
                    d: getattr(profile, d) for d in DIMENSIONS
                }
                current_profile["entries"] = profile.entries
                current_profile["tag_weights"] = profile.tag_weights
                current_profile["stability_counter"] = profile.stability_counter
                current_profile["audit_counter"] = profile.audit_counter
                return {
                    "current_profile": current_profile,
                    "profile_changed": changed,
                }
        except Exception as e:
            logger.warning(f"DB merge failed: {e}, using in-memory merge")
            old = state.get("current_profile", {})
            merged, changed = self._merge_in_memory(old, fragment)
            return {
                "current_profile": merged,
                "profile_changed": changed,
            }

    # ── audit ────────────────────────────────────────────────────────

    async def _audit_node(self, state: ProfileState) -> dict:
        """周期性审计：LLM 审视已有条目是否仍成立"""
        profile = state.get("current_profile", {})
        audit_counter = profile.get("audit_counter", 0)

        if audit_counter < AUDIT_INTERVAL:
            return {}

        # 检查是否有条目可审计
        entries = profile.get("entries", {})
        all_entries = entries.get("weak_points", []) + entries.get("interest_direction", [])
        if not all_entries:
            return {}

        # 收集最近对话摘要
        messages = state.get("messages", [])
        recent_summary = self._format_recent_summary(messages)

        result = await self._run_audit(all_entries, recent_summary)
        if result:
            try:
                async with get_db() as session:
                    db_result = await session.execute(
                        select(StudentProfile).where(
                            StudentProfile.user_id == state.get("user_id", 1)
                        )
                    )
                    db_profile = db_result.scalar_one_or_none()
                    if db_profile:
                        db_entries = dict(db_profile.entries or {})
                        for dim in ARRAY_DIMENSIONS:
                            dim_entries = [
                                e for e in db_entries.get(dim, [])
                                if e.get("text", "") not in result.get("delete_texts", set())
                            ]
                            # 应用更新
                            for update in result.get("updates", []):
                                for i, e in enumerate(dim_entries):
                                    if e.get("text") == update.get("old_text"):
                                        dim_entries[i] = {
                                            **e,
                                            "text": update.get("new_text", e.get("text")),
                                            "updated_at": _now_iso(),
                                        }
                            db_entries[dim] = dim_entries
                        db_profile.entries = db_entries
                        db_profile.audit_counter = 0
                        await session.commit()

                        new_profile = dict(profile)
                        new_profile["entries"] = db_entries
                        new_profile["audit_counter"] = 0
                        return {"current_profile": new_profile, "profile_changed": True}
            except Exception as e:
                logger.warning(f"Audit DB update failed: {e}")

        return {}

    # ── response ─────────────────────────────────────────────────────

    async def _response_node(self, state: ProfileState) -> dict:
        """LLM 基于当前画像生成个性化回复"""
        messages = state.get("messages", [])
        current_profile = state.get("current_profile", {})

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

    # ── merge logic ──────────────────────────────────────────────────

    def _apply_merge(self, profile: StudentProfile, fragment: dict) -> bool:
        """将 fragment 合并到 ORM 对象，返回是否发生变化"""
        changed = False

        # ── ARRAY 维度：条目模型 ──
        db_entries = dict(profile.entries or {})

        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue

            dim_entries = list(db_entries.get(dim, []))
            now = _now_iso()

            for item in new_items:
                text = item if isinstance(item, str) else item.get("text", "")
                if not text:
                    continue

                # 尝试匹配已有条目（bigram 相似度）
                matched = False
                for existing in dim_entries:
                    if _bigram_jaccard(text, existing.get("text", "")) > DEDUP_SIMILARITY:
                        existing["confidence"] = min(existing.get("confidence", 1) + 1, 10)
                        existing["updated_at"] = now
                        if existing["confidence"] >= MIN_CONFIDENCE_FOR_ACTIVE:
                            existing["status"] = "active"
                        matched = True
                        break

                if not matched:
                    dim_entries.append({
                        "text": text,
                        "confidence": 1,
                        "status": "tentative",
                        "created_at": now,
                        "updated_at": now,
                    })

            # 裁剪到上限：active > tentative > stale，同状态按置信度降序
            if len(dim_entries) > MAX_ENTRIES_PER_DIM:
                status_order = {"active": 0, "tentative": 1, "stale": 2}
                dim_entries.sort(
                    key=lambda e: (
                        status_order.get(e.get("status", "active"), 0),
                        -e.get("confidence", 1),
                    )
                )
                dim_entries = dim_entries[:MAX_ENTRIES_PER_DIM]

            db_entries[dim] = dim_entries
            changed = True

            # 向后兼容：同步旧版 list 字段（按置信度降序）
            legacy = sorted(
                [e["text"] for e in dim_entries],
                key=lambda t: next(
                    (e["confidence"] for e in dim_entries if e["text"] == t), 1
                ),
                reverse=True,
            )
            if legacy != getattr(profile, dim):
                setattr(profile, dim, legacy)

        if db_entries != (profile.entries or {}):
            profile.entries = db_entries
            changed = True

        # ── NUMBER 维度：EMA（保持不变）──
        for dim in NUMBER_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
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

        # ── REPLACE 维度：稳定性计数器（保持不变）──
        stability = dict(profile.stability_counter or {})
        for dim in REPLACE_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
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

        if stability != (profile.stability_counter or {}):
            profile.stability_counter = stability
            changed = True

        return changed

    def _merge_in_memory(self, old: dict, fragment: dict) -> tuple[dict, bool]:
        """纯内存合并（DB 不可用时的降级）"""
        merged = dict(old)
        changed = False

        entries = dict(old.get("entries", {}))

        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue

            dim_entries = list(entries.get(dim, []))
            now = _now_iso()

            for item in new_items:
                text = item if isinstance(item, str) else item.get("text", "")
                if not text:
                    continue

                matched = False
                for existing in dim_entries:
                    if _bigram_jaccard(text, existing.get("text", "")) > DEDUP_SIMILARITY:
                        existing["confidence"] = min(existing.get("confidence", 1) + 1, 10)
                        existing["updated_at"] = now
                        if existing["confidence"] >= MIN_CONFIDENCE_FOR_ACTIVE:
                            existing["status"] = "active"
                        matched = True
                        break

                if not matched:
                    dim_entries.append({
                        "text": text,
                        "confidence": 1,
                        "status": "tentative",
                        "created_at": now,
                        "updated_at": now,
                    })

            if len(dim_entries) > MAX_ENTRIES_PER_DIM:
                status_order = {"active": 0, "tentative": 1, "stale": 2}
                dim_entries.sort(
                    key=lambda e: (
                        status_order.get(e.get("status", "active"), 0),
                        -e.get("confidence", 1),
                    )
                )
                dim_entries = dim_entries[:MAX_ENTRIES_PER_DIM]

            entries[dim] = dim_entries
            changed = True

            legacy = sorted(
                [e["text"] for e in dim_entries],
                key=lambda t: next(
                    (e["confidence"] for e in dim_entries if e["text"] == t), 1
                ),
                reverse=True,
            )
            if legacy != merged.get(dim):
                merged[dim] = legacy

        if entries != old.get("entries", {}):
            merged["entries"] = entries

        # NUMBER: EMA
        for dim in NUMBER_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
            try:
                new_num = float(new_val)
            except (TypeError, ValueError):
                continue
            old_val = merged.get(dim)
            merged[dim] = int(old_val * 0.7 + new_num * 0.3) if old_val is not None else int(new_num)
            if merged[dim] != old_val:
                changed = True

        # REPLACE: 稳定性
        inmem_stability = dict(old.get("stability_counter", {}))
        for dim in REPLACE_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
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

        if inmem_stability != old.get("stability_counter", {}):
            merged["stability_counter"] = inmem_stability

        return merged, changed

    # ── audit logic ──────────────────────────────────────────────────

    async def _run_audit(
        self, entries: list[dict], recent_summary: str
    ) -> dict | None:
        """LLM 审计：审视已有条目是否仍成立"""
        entries_text = self._format_entries_for_audit(entries)

        audit_prompt = self._load_extra_prompt("audit.yaml", key="user_template")
        user_prompt = interpolate_variables(
            audit_prompt,
            {
                "entries": entries_text,
                "recent_summary": recent_summary,
            },
        )

        system_prompt = self._load_extra_prompt("audit.yaml", key="system")

        try:
            result_text = await self.audit_llm.chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )
            from app.utils.json_parser import parse_llm_json
            data = parse_llm_json(result_text, fallback={})
            if not isinstance(data, dict):
                data = {}

            delete_texts = set(data.get("delete", []))
            updates = data.get("update", [])

            return {"delete_texts": delete_texts, "updates": updates}
        except Exception as e:
            logger.warning(f"Audit LLM failed: {e}")
            return None

    # ── formatters ───────────────────────────────────────────────────

    def _format_new_messages(self, messages: list[dict]) -> str:
        """格式化本轮新消息为文本"""
        lines = []
        for i, m in enumerate(messages):
            role = "学生" if m.get("role") == "user" else "AI"
            content = m.get("content", "")
            lines.append(f"[{role}#{i}]: {content}")
        return "\n".join(lines)

    def _format_entries_for_extract(self, entries: dict) -> str:
        """格式化已有条目为 extract 的上下文（去重依据）"""
        if not entries:
            return "（尚无画像条目，这是第一次构建画像）"

        lines = ["已有画像条目（不要重复以下信息！提取新的或不一致的变化）："]
        labels = {"weak_points": "薄弱环节", "interest_direction": "兴趣方向"}
        for dim, label in labels.items():
            dim_entries = entries.get(dim, [])
            if dim_entries:
                lines.append(f"\n  {label}:")
                for e in dim_entries:
                    conf = e.get("confidence", 1)
                    status = e.get("status", "active")
                    mark = "✓" if status == "active" else "?"
                    lines.append(f"    [{mark} c={conf}] {e.get('text', '')}")
        return "\n".join(lines)

    def _format_entries_for_audit(self, entries: list[dict]) -> str:
        """格式化条目供审计 LLM 审视"""
        lines = []
        for i, e in enumerate(entries):
            status = e.get("status", "active")
            conf = e.get("confidence", 1)
            text = e.get("text", "")
            lines.append(f"  [{i}] [{status} c={conf}] {text}")
        return "\n".join(lines) if lines else "（空）"

    def _format_recent_summary(self, messages: list[dict]) -> str:
        """格式化最近对话作为审计上下文"""
        recent = messages[-12:] if len(messages) > 12 else messages
        lines = []
        for m in recent:
            role = "学生" if m.get("role") == "user" else "AI"
            content = m.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    def _format_profile_for_response(self, profile: dict) -> str:
        """将画像 dict 格式化为 LLM 可读的文本"""
        if not profile or all(
            v is None or v == [] or v == {}
            for k, v in profile.items()
            if k not in ("tag_weights", "stability_counter", "entries", "audit_counter")
        ):
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

        entries = profile.get("entries", {})

        for dim, label in labels.items():
            val = profile.get(dim)
            if dim in ARRAY_DIMENSIONS:
                dim_entries = entries.get(dim, [])
                if dim_entries:
                    parts = []
                    for e in dim_entries[:6]:
                        conf = e.get("confidence", 1)
                        status = "✓" if e.get("status") == "active" else "?"
                        text = e.get("text", "")
                        if len(text) > 80:
                            text = text[:80] + "..."
                        parts.append(f"{status}{text}(c={conf})")
                    val = "、".join(parts)
                elif val and isinstance(val, list):
                    val = "、".join(val[:6])
                else:
                    val = None
            elif dim == "knowledge_base" and isinstance(val, (int, float)):
                val = f"{val}/100"
            elif not val:
                continue
            lines.append(f"  - {label}: {val}")

        return "\n".join(lines)

    # ── parsing ──────────────────────────────────────────────────────

    async def _load_last_extracted_index(self, user_id: int) -> int:
        """从 DB 加载上次提取的消息索引"""
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(
                        StudentProfile.user_id == user_id
                    )
                )
                profile = result.scalar_one_or_none()
                return (profile.last_extracted_msg_index or 0) if profile else 0
        except Exception:
            return 0

    def _parse_extract_result(self, text: str) -> dict:
        """解析 LLM 输出的 JSON"""
        from app.utils.json_parser import parse_llm_json

        data = parse_llm_json(text, fallback={})
        if not isinstance(data, dict):
            data = {}
        updates = data.get("updates", data)
        return {k: v for k, v in updates.items() if k in DIMENSIONS}

    # ── 公开方法：供 tutor/unified chat 后台调用 ───────────────────

    async def extract_and_merge(
        self, user_id: int, messages: list[dict], current_profile: dict | None = None,
    ) -> dict:
        """后台增量画像提取 + 合并（不跑 director/response，不阻塞主流程）。

        供 tutor_chat、unified_chat 等非画像对话在响应结束后异步调用，
        从当前轮对话中提取画像信号并持久化。

        Returns:
            {"changed": bool, "profile": dict}
        """
        if not messages:
            return {"changed": False, "profile": current_profile or {}}

        if current_profile is None:
            current_profile = await self._load_profile_dict(user_id)

        last_idx = await self._load_last_extracted_index(user_id)

        state: ProfileState = {
            "messages": messages,
            "user_id": user_id,
            "current_profile": current_profile,
            "last_extracted_msg_index": last_idx,
        }

        extract_result = await self._extract_node(state)
        fragment = extract_result.get("extracted_fragment", {})
        if not fragment:
            return {"changed": False, "profile": current_profile}

        merge_state: ProfileState = {
            "messages": messages,
            "user_id": user_id,
            "current_profile": current_profile,
            "extracted_fragment": fragment,
            "last_extracted_msg_index": extract_result.get("last_extracted_msg_index", last_idx),
        }
        merge_result = await self._merge_node(merge_state)

        profile = merge_result.get("current_profile", current_profile)
        changed = merge_result.get("profile_changed", False)

        if changed:
            logger.info(
                "Background profile update: user_id=%d, dimensions=%s",
                user_id,
                [k for k, v in fragment.items() if v],
            )

        return {"changed": changed, "profile": profile}

    async def _load_profile_dict(self, user_id: int) -> dict:
        try:
            async with get_db() as session:
                result = await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
                if profile:
                    p = {d: getattr(profile, d) for d in DIMENSIONS}
                    p["entries"] = profile.entries
                    p["tag_weights"] = profile.tag_weights
                    p["stability_counter"] = profile.stability_counter
                    p["audit_counter"] = profile.audit_counter
                    return p
        except Exception:
            pass
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
