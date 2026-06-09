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

from app.agents.base_agent import BaseAgent
from app.services.java_api_client import get_java_client
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

MAX_ENTRIES_PER_DIM = 8
MIN_CONFIDENCE_FOR_ACTIVE = 2
AUDIT_INTERVAL = 10
DEDUP_SIMILARITY = 0.55

TAG_EMA_ALPHA = 0.4
TAG_CUTOFF = 0.2
STABILITY_N = 3

MAX_EXTRACT_TURNS = 10


def _bigram_jaccard(a: str, b: str) -> float:
    """字符 bigram 包含相似度"""
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
        self._client = get_java_client()

        self.extract_system_template = self._load_prompt(filename="extract.yaml", key="system")
        self.extract_user_template = self._load_prompt(filename="extract.yaml", key="user")

        self.extract_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)
        self.response_llm = create_llm(temperature=0.7, use_mock=use_mock_llm)
        self.audit_llm = create_llm(temperature=0.2, use_mock=use_mock_llm)

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
        messages = state.get("messages", [])
        user_id = state.get("user_id", 1)
        last_idx = state.get("last_extracted_msg_index")

        if last_idx is None:
            last_idx = await self._load_last_extracted_index(user_id)

        new_start = min(last_idx, len(messages))
        new_messages = messages[new_start:]

        if not new_messages:
            return {"extracted_fragment": {}, "last_extracted_msg_index": last_idx}

        if len(new_messages) > MAX_EXTRACT_TURNS:
            new_messages = new_messages[-MAX_EXTRACT_TURNS:]
            new_start = len(messages) - len(new_messages)

        current_profile = state.get("current_profile", {})
        entries = current_profile.get("entries", {})
        entries_summary = self._format_entries_for_extract(entries)

        new_messages_text = self._format_new_messages(new_messages)
        extract_user_prompt = interpolate_variables(
            self.extract_user_template,
            {"existing_entries": entries_summary, "new_messages": new_messages_text},
        )

        extract_messages = [{"role": "user", "content": extract_user_prompt}]

        try:
            result_text = await self.extract_llm.chat(
                extract_messages, system_prompt=self.extract_system_template,
            )
            fragment = self._parse_extract_result(result_text)
        except (RuntimeError, ConnectionError) as e:
            logger.error(f"Extract LLM failed: {e}, using empty fragment")
            fragment = {}

        new_last_idx = new_start + len(new_messages)

        return {"extracted_fragment": fragment, "last_extracted_msg_index": new_last_idx}

    # ── merge ────────────────────────────────────────────────────────

    async def _merge_node(self, state: ProfileState) -> dict:
        user_id = state.get("user_id", 1)
        fragment = state.get("extracted_fragment", {})

        if not fragment:
            return {
                "current_profile": state.get("current_profile", {}),
                "profile_changed": False,
            }

        try:
            profile = await self._load_profile_dict(user_id)
            is_new = not profile
            if is_new:
                profile = {"user_id": user_id}

            new_last_idx = state.get("last_extracted_msg_index", 0)
            if new_last_idx > (profile.get("last_extracted_msg_index") or 0):
                profile["last_extracted_msg_index"] = new_last_idx

            profile, changed = self._apply_merge_in_memory(profile, fragment)

            profile["raw_profile_json"] = {
                d: profile.get(d) for d in DIMENSIONS
            }
            profile["raw_profile_json"]["entries"] = profile.get("entries")
            profile["raw_profile_json"]["tag_weights"] = profile.get("tag_weights")
            profile["raw_profile_json"]["stability_counter"] = profile.get("stability_counter")

            profile["audit_counter"] = (profile.get("audit_counter") or 0) + 1

            if is_new:
                await self._client.upsert_profile(user_id, profile)
            elif changed:
                await self._client.update_profile(user_id, profile)

            current_profile = {
                d: profile.get(d) for d in DIMENSIONS
            }
            current_profile["entries"] = profile.get("entries")
            current_profile["tag_weights"] = profile.get("tag_weights")
            current_profile["stability_counter"] = profile.get("stability_counter")
            current_profile["audit_counter"] = profile.get("audit_counter")
            return {"current_profile": current_profile, "profile_changed": changed}
        except Exception as e:
            logger.warning(f"Profile merge failed: {e}, using in-memory merge")
            old = state.get("current_profile", {})
            merged, changed = self._merge_in_memory(old, fragment)
            return {"current_profile": merged, "profile_changed": changed}

    # ── audit ────────────────────────────────────────────────────────

    async def _audit_node(self, state: ProfileState) -> dict:
        profile = state.get("current_profile", {})
        audit_counter = profile.get("audit_counter", 0)

        if audit_counter < AUDIT_INTERVAL:
            return {}

        entries = profile.get("entries", {})
        all_entries = entries.get("weak_points", []) + entries.get("interest_direction", [])
        if not all_entries:
            return {}

        messages = state.get("messages", [])
        recent_summary = self._format_recent_summary(messages)

        result = await self._run_audit(all_entries, recent_summary)
        if result:
            try:
                db_entries = dict(entries)
                for dim in ARRAY_DIMENSIONS:
                    dim_entries = [
                        e for e in db_entries.get(dim, [])
                        if e.get("text", "") not in result.get("delete_texts", set())
                    ]
                    for update in result.get("updates", []):
                        for i, e in enumerate(dim_entries):
                            if e.get("text") == update.get("old_text"):
                                dim_entries[i] = {**e, "text": update.get("new_text", e.get("text")), "updated_at": _now_iso()}
                    db_entries[dim] = dim_entries

                new_profile = dict(profile)
                new_profile["entries"] = db_entries
                new_profile["audit_counter"] = 0

                await self._client.update_profile(
                    state.get("user_id", 1),
                    {"entries": db_entries, "audit_counter": 0},
                )
                return {"current_profile": new_profile, "profile_changed": True}
            except Exception as e:
                logger.warning(f"Audit update failed: {e}")

        return {}

    # ── response ─────────────────────────────────────────────────────

    async def _response_node(self, state: ProfileState) -> dict:
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

    # ── merge logic (in-memory) ──────────────────────────────────────

    @staticmethod
    def _merge_array_dimension(entries: dict, dim: str, new_items: list) -> tuple[dict, list, bool]:
        """合并单一 ARRAY 维度的条目。返回 (更新后的 entries, legacy 列表, 是否变更)"""
        dim_entries = list(entries.get(dim, []))
        now = _now_iso()
        changed = False

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
                    "text": text, "confidence": 1, "status": "tentative",
                    "created_at": now, "updated_at": now,
                })
                changed = True

        if len(dim_entries) > MAX_ENTRIES_PER_DIM:
            status_order = {"active": 0, "tentative": 1, "stale": 2}
            dim_entries.sort(
                key=lambda e: (status_order.get(e.get("status", "active"), 0), -e.get("confidence", 1))
            )
            dim_entries = dim_entries[:MAX_ENTRIES_PER_DIM]
            changed = True

        legacy = sorted(
            [e["text"] for e in dim_entries],
            key=lambda t: next((e["confidence"] for e in dim_entries if e["text"] == t), 1),
            reverse=True,
        )

        new_entries = dict(entries)
        new_entries[dim] = dim_entries
        return new_entries, legacy, changed or (dim_entries != entries.get(dim))

    def _apply_merge_in_memory(self, profile: dict, fragment: dict) -> tuple[dict, bool]:
        """纯内存合并，返回 (new_profile, changed) — 不改变传入参数"""
        new_profile = dict(profile)
        changed = False

        db_entries = dict(new_profile.get("entries", {}))

        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue

            db_entries, legacy, dim_changed = self._merge_array_dimension(
                db_entries, dim, new_items,
            )
            if dim_changed:
                changed = True
            if legacy != new_profile.get(dim):
                new_profile[dim] = legacy

        if db_entries != (new_profile.get("entries") or {}):
            new_profile["entries"] = db_entries
            changed = True

        for dim in NUMBER_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
            try:
                new_num = float(new_val)
            except (TypeError, ValueError):
                continue
            old_val = new_profile.get(dim)
            merged = int(old_val * 0.7 + new_num * 0.3) if old_val is not None else int(new_num)
            if merged != old_val:
                new_profile[dim] = merged
                changed = True

        stability = dict(new_profile.get("stability_counter", {}))
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
            if sc["count"] >= STABILITY_N and new_val != new_profile.get(dim):
                new_profile[dim] = new_val
                changed = True
                stability[dim] = {"value": new_val, "count": 0}

        if stability != (new_profile.get("stability_counter") or {}):
            new_profile["stability_counter"] = stability
            changed = True

        return new_profile, changed

    def _merge_in_memory(self, old: dict, fragment: dict) -> tuple[dict, bool]:
        """纯内存合并（网络不可用时的降级）"""
        merged = dict(old)
        changed = False

        entries = dict(old.get("entries", {}))

        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue

            entries, legacy, dim_changed = self._merge_array_dimension(
                entries, dim, new_items,
            )
            if dim_changed:
                changed = True
            if legacy != merged.get(dim):
                merged[dim] = legacy

        if entries != old.get("entries", {}):
            merged["entries"] = entries

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

    async def _run_audit(self, entries: list[dict], recent_summary: str) -> dict | None:
        entries_text = self._format_entries_for_audit(entries)

        audit_prompt = self._load_extra_prompt("audit.yaml", key="user_template")
        user_prompt = interpolate_variables(
            audit_prompt, {"entries": entries_text, "recent_summary": recent_summary},
        )
        system_prompt = self._load_extra_prompt("audit.yaml", key="system")

        try:
            result_text = await self.audit_llm.chat(
                [{"role": "user", "content": user_prompt}], system_prompt=system_prompt,
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
        lines = []
        for i, m in enumerate(messages):
            role = "学生" if m.get("role") == "user" else "AI"
            content = m.get("content", "")
            lines.append(f"[{role}#{i}]: {content}")
        return "\n".join(lines)

    def _format_entries_for_extract(self, entries: dict) -> str:
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
        lines = []
        for i, e in enumerate(entries):
            status = e.get("status", "active")
            conf = e.get("confidence", 1)
            text = e.get("text", "")
            lines.append(f"  [{i}] [{status} c={conf}] {text}")
        return "\n".join(lines) if lines else "（空）"

    def _format_recent_summary(self, messages: list[dict]) -> str:
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
        try:
            profile = await self._client.get_profile(user_id)
            return (profile.get("last_extracted_msg_index") or 0) if profile else 0
        except Exception:
            return 0

    def _parse_extract_result(self, text: str) -> dict:
        from app.utils.json_parser import parse_llm_json

        data = parse_llm_json(text, fallback={})
        if not isinstance(data, dict):
            data = {}
        updates = data.get("updates", data)
        return {k: v for k, v in updates.items() if k in DIMENSIONS}

    async def _load_profile_dict(self, user_id: int) -> dict:
        try:
            profile = await self._client.get_profile(user_id)
            if profile:
                p = {d: profile.get(d) for d in DIMENSIONS}
                p["entries"] = profile.get("entries")
                p["tag_weights"] = profile.get("tag_weights")
                p["stability_counter"] = profile.get("stability_counter")
                p["audit_counter"] = profile.get("audit_counter")
                p["last_extracted_msg_index"] = profile.get("last_extracted_msg_index")
                return p
        except Exception:
            pass
        return {}

    # ── 公开方法：供 tutor/unified chat 后台调用 ───────────────────

    async def extract_and_merge(
        self, user_id: int, messages: list[dict], current_profile: dict | None = None,
    ) -> dict:
        """后台增量画像提取 + 合并"""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
