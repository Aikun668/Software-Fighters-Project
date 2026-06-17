"""
ProfileAgent — 对话式学习画像构建智能体

借鉴 DeepTutor L3 profile 更新机制：
  - 增量提取：只处理上次提取后的新消息，不重复处理旧消息
  - 条目模型：ARRAY 维度存储完整句子条目 + 置信度，而非孤立标签
  - 周期性审计：LLM 审视已有条目是否仍成立
  - 硬上限裁剪：每维度最多 N 个条目

6 节点 StateGraph：extract → semantic_judge → merge → audit → response

Architecture #2: 纯内存计算。Java 传入 profile dict，Python 返回更新结果，
不调 Java API，不持久化。
"""

import logging
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import StateGraph

from app.agents.base_agent import BaseAgent
from app.services.llm_service import create_llm, OpenAILLM, PROFILE_DIRECTOR
from app.utils.embeddings import semantic_similarity
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
AUDIT_MSG_INTERVAL = 20
DEDUP_PREFILTER = 0.45  # embedding recall threshold (candidate only, final decision by LLM)

TAG_EMA_ALPHA = 0.4
TAG_CUTOFF = 0.2
STABILITY_N = 2

MAX_EXTRACT_TURNS = 10


class ProfileState(TypedDict, total=False):
    messages: list[dict]
    user_id: int
    current_profile: dict
    extracted_fragment: dict
    judge_result: dict
    profile_changed: bool
    response: str
    last_extracted_msg_index: int


class ProfileAgent(BaseAgent):
    """对话式学习画像构建智能体 — 纯内存计算"""

    def __init__(self, config=None, use_mock_llm: bool = False):
        super().__init__(
            agent_name="profile_agent",
            module="agents",
            language="zh",
            config=config,
            use_mock_llm=use_mock_llm,
        )
        self.use_mock_llm = use_mock_llm

        self.extract_system_template = self._load_prompt(filename="extract.yaml", key="system")
        self.extract_user_template = self._load_prompt(filename="extract.yaml", key="user")

        self.extract_llm = create_llm(temperature=0.3, use_mock=use_mock_llm)
        self.response_llm = create_llm(temperature=0.4, use_mock=use_mock_llm)
        self.audit_llm = create_llm(temperature=0.2, use_mock=use_mock_llm)

        # 语义 judge 必须走 DeepSeek V4 Flash (DashScope OpenAI 兼容接口)
        # create_llm 默认走星火，无法传递 model/api_key/base_url → 直接实例化 OpenAILLM
        self.judge_llm = OpenAILLM(
            temperature=PROFILE_DIRECTOR.default.temperature,
            max_tokens=1024,  # override: 256 too low for multi-candidate JSON
            use_mock=use_mock_llm,
            model=PROFILE_DIRECTOR.default.model,
            api_key=PROFILE_DIRECTOR.default.api_key,
            base_url=PROFILE_DIRECTOR.default.base_url,
        )
        self.judge_system_template = self._load_prompt(
            filename="semantic_judge.yaml", key="system",
        )
        self.judge_user_template = self._load_prompt(
            filename="semantic_judge.yaml", key="user",
        )

    def build_graph(self):
        graph = StateGraph(ProfileState)

        graph.add_node("extract", self._extract_node)
        graph.add_node("semantic_judge", self._semantic_judge_node)
        graph.add_node("merge", self._merge_node)
        graph.add_node("audit", self._audit_node)
        graph.add_node("response", self._response_node)

        graph.set_entry_point("extract")
        graph.add_edge("extract", "semantic_judge")
        graph.add_edge("semantic_judge", "merge")
        graph.add_edge("merge", "audit")
        graph.add_edge("audit", "response")
        graph.set_finish_point("response")

        return graph.compile()

    # ── extract ─────────────────────────────────────────────────────

    async def _extract_node(self, state: ProfileState) -> dict:
        messages = state.get("messages", [])
        current_profile = state.get("current_profile", {})
        last_idx = state.get("last_extracted_msg_index")

        if last_idx is None:
            last_idx = current_profile.get("last_extracted_msg_index") or 0

        new_start = min(last_idx, len(messages))
        new_messages = messages[new_start:]

        if not new_messages:
            return {"extracted_fragment": {}, "last_extracted_msg_index": last_idx}

        if len(new_messages) > MAX_EXTRACT_TURNS:
            new_messages = new_messages[-MAX_EXTRACT_TURNS:]
            new_start = len(messages) - len(new_messages)

        entries = current_profile.get("entries") or {}
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
        fragment = state.get("extracted_fragment", {})

        if not fragment:
            return {
                "current_profile": state.get("current_profile", {}),
                "profile_changed": False,
            }

        profile = state.get("current_profile", {})
        if not profile:
            profile = {}

        new_last_idx = state.get("last_extracted_msg_index", 0)
        if new_last_idx > (profile.get("last_extracted_msg_index") or 0):
            profile["last_extracted_msg_index"] = new_last_idx

        profile, changed = self._apply_merge_in_memory(
            profile, fragment, state.get("judge_result"),
        )

        profile["raw_profile_json"] = {
            d: profile.get(d) for d in DIMENSIONS
        }
        profile["raw_profile_json"]["entries"] = profile.get("entries")
        profile["raw_profile_json"]["tag_weights"] = profile.get("tag_weights")
        profile["raw_profile_json"]["stability_counter"] = profile.get("stability_counter")

        current_profile = {
            d: profile.get(d) for d in DIMENSIONS
        }
        current_profile["entries"] = profile.get("entries")
        current_profile["tag_weights"] = profile.get("tag_weights")
        current_profile["stability_counter"] = profile.get("stability_counter")
        current_profile["last_extracted_msg_index"] = profile.get("last_extracted_msg_index")
        current_profile["last_audit_msg_index"] = profile.get("last_audit_msg_index")
        return {"current_profile": current_profile, "profile_changed": changed}

    # ── semantic_judge ────────────────────────────────────────────────

    async def _semantic_judge_node(self, state: ProfileState) -> dict:
        """merge 前调用 flash LLM 做语义去重判断。embedding 只做候选召回。"""
        fragment = state.get("extracted_fragment", {})
        profile = state.get("current_profile", {})

        if not fragment:
            return {"judge_result": {}}

        judge_tasks = self._build_judge_tasks(profile, fragment)
        if not judge_tasks:
            return {"judge_result": {}}

        judge_user_prompt = interpolate_variables(
            self.judge_user_template, {"judge_tasks": judge_tasks},
        )

        try:
            result_text = await self.judge_llm.chat(
                [{"role": "user", "content": judge_user_prompt}],
                system_prompt=self.judge_system_template,
            )
            judge_result = self._parse_judge_result(result_text)
        except Exception as e:
            logger.warning("Semantic judge LLM failed: %s, falling back to embedding", e)
            judge_result = {}

        return {"judge_result": judge_result}

    def _build_judge_tasks(self, profile: dict, fragment: dict) -> str | None:
        """构建语义判断的 tasks 文本。无待判断项时返回 None。

        embedding 做候选召回（t=0.45）：新条目与已有条目无候选时不送 LLM，自动创建。
        """
        entries = profile.get("entries", {})
        dim_labels = {
            "weak_points": "薄弱环节", "interest_direction": "兴趣方向",
            "cognitive_style": "学习风格", "learning_goal": "学习目标",
            "learning_pace": "学习节奏",
        }
        parts = []

        # ARRAY 候选任务
        array_sections = []
        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue
            existing = entries.get(dim, [])
            if not existing:
                continue

            existing_lines = [
                f"  [{i}] \"{e.get('text', '')}\" (c={e.get('confidence', 1)})"
                for i, e in enumerate(existing)
            ]

            # Pre-filter: only include new items with at least one candidate above threshold
            new_lines = []
            for i, item in enumerate(new_items):
                text = item if isinstance(item, str) else item.get("text", "")
                if not text:
                    continue
                has_candidate = any(
                    semantic_similarity(text, e.get("text", "")) > DEDUP_PREFILTER
                    for e in existing
                )
                if has_candidate:
                    nid = chr(ord('A') + i)
                    new_lines.append(f"  [{nid}] \"{text}\"")
                # No candidate → auto-create, skip LLM judgment

            if new_lines:
                section = f"【{dim}（{dim_labels.get(dim, dim)}）】\n已有条目：\n"
                section += "\n".join(existing_lines)
                section += "\n\n本轮新条目（已通过 embedding 候选召回）：\n"
                section += "\n".join(new_lines)
                array_sections.append(section)

        if array_sections:
            parts.append("## ARRAY 去重任务\n")
            parts.append("\n\n".join(array_sections))

        # REPLACE 分类任务
        replace_tasks = []
        for dim in REPLACE_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
            old_val = profile.get(dim)
            if old_val is None or old_val == new_val:
                continue
            replace_tasks.append(
                f"- {dim}（{dim_labels.get(dim, dim)}）: 旧值\"{old_val}\" vs 新值\"{new_val}\""
            )

        if replace_tasks:
            parts.append("\n## REPLACE 维度分类任务\n")
            parts.append("\n".join(replace_tasks))

        if not parts:
            return None

        return "\n".join(parts)

    def _parse_judge_result(self, text: str) -> dict:
        """解析 judge LLM 返回的 JSON"""
        from app.utils.json_parser import parse_llm_json

        data = parse_llm_json(text, fallback={})
        if not isinstance(data, dict):
            data = {}
        return {
            "array_matches": data.get("array_matches", []),
            "replace_classifications": data.get("replace_classifications", []),
        }

    # ── audit ────────────────────────────────────────────────────────

    async def _audit_node(self, state: ProfileState) -> dict:
        profile = state.get("current_profile", {})
        last_audit_idx = profile.get("last_audit_msg_index") or 0
        current_idx = profile.get("last_extracted_msg_index") or 0
        msgs_since_audit = current_idx - last_audit_idx

        if msgs_since_audit < AUDIT_MSG_INTERVAL:
            return {}

        entries = profile.get("entries", {})
        all_entries = entries.get("weak_points", []) + entries.get("interest_direction", [])
        if not all_entries:
            return {}

        messages = state.get("messages", [])
        recent_summary = self._format_recent_summary(messages)

        result = await self._run_audit(all_entries, recent_summary)
        if result:
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
            new_profile["last_audit_msg_index"] = current_idx

            return {"current_profile": new_profile, "profile_changed": True}

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
    def _merge_array_dimension(entries: dict, dim: str, new_items: list, judge_matches: dict = None) -> tuple[dict, list, bool]:
        """合并单一 ARRAY 维度的条目。judge_matches: {text: existing_index | None}"""
        dim_entries = list(entries.get(dim, []))
        now = _now_iso()
        changed = False

        for item in new_items:
            text = item if isinstance(item, str) else item.get("text", "")
            if not text:
                continue

            match_index = None
            if judge_matches is not None:
                match_index = judge_matches.get(text)
            else:
                for i, existing in enumerate(dim_entries):
                    if semantic_similarity(text, existing.get("text", "")) > 0.70:
                        match_index = i
                        break

            if match_index is not None and 0 <= match_index < len(dim_entries):
                existing = dim_entries[match_index]
                existing["confidence"] = min(existing.get("confidence", 1) + 1, 10)
                existing["updated_at"] = now
                if existing["confidence"] >= MIN_CONFIDENCE_FOR_ACTIVE:
                    existing["status"] = "active"
            else:
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

    def _apply_merge_in_memory(self, profile: dict, fragment: dict, judge_result: dict = None) -> tuple[dict, bool]:
        """纯内存合并，返回 (new_profile, changed)。judge_result 来自 semantic_judge LLM。"""
        new_profile = dict(profile)
        changed = False

        if "entries" not in new_profile:
            new_profile["entries"] = {}
        db_entries = dict(new_profile["entries"] or {})

        for dim in ARRAY_DIMENSIONS:
            new_items = fragment.get(dim)
            if not new_items or not isinstance(new_items, list):
                continue

            dim_judge_matches = None
            if judge_result:
                array_matches = judge_result.get("array_matches", [])
                dim_judge_matches = {}
                for m in array_matches:
                    if not isinstance(m, dict):
                        continue
                    if m.get("dim") != dim:
                        continue
                    text = m.get("new_text", "")
                    if text:
                        dim_judge_matches[text] = m.get("match_existing_index")

            db_entries, legacy, dim_changed = self._merge_array_dimension(
                db_entries, dim, new_items, dim_judge_matches,
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
            if old_val is None:
                merged = int(new_num)
            else:
                merged = int(old_val * 0.7 + new_num * 0.3)
            if merged != old_val:
                new_profile[dim] = merged
                changed = True

        stability = dict((new_profile or {}).get("stability_counter") or {})
        for dim in REPLACE_DIMENSIONS:
            new_val = fragment.get(dim)
            if new_val is None:
                continue
            current_value = new_profile.get(dim)
            default_sc = {"value": None, "count": 0, "status": None, "pending_value": None}
            sc = dict(stability.get(dim, default_sc))

            if current_value == new_val:
                sc = {"value": new_val, "count": 0, "status": "confirmed", "pending_value": None}
            elif current_value is None:
                # 首次填充直接确认
                new_profile[dim] = new_val
                sc = {"value": new_val, "count": 0, "status": "confirmed", "pending_value": None}
                changed = True
            else:
                relation = "contradiction"
                if judge_result:
                    for rc in judge_result.get("replace_classifications", []):
                        if isinstance(rc, dict) and rc.get("dim") == dim:
                            relation = rc.get("relation", "contradiction")
                            break

                if relation == "identical":
                    sc = {"value": new_val, "count": 0, "status": "confirmed", "pending_value": None}
                elif relation == "refinement":
                    new_profile[dim] = new_val
                    sc = {"value": new_val, "count": 0, "status": "confirmed", "pending_value": None}
                    changed = True
                else:  # contradiction, required=STABILITY_N
                    pending = sc.get("pending_value")
                    if pending is not None and semantic_similarity(pending, new_val) > 0.80:
                        sc["count"] = sc.get("count", 1) + 1
                    else:
                        sc = {"value": current_value, "pending_value": new_val,
                              "count": 1, "status": "tentative"}

                    if sc["count"] >= STABILITY_N:
                        new_profile[dim] = new_val
                        sc = {"value": new_val, "count": 0, "status": "confirmed", "pending_value": None}
                        changed = True

            stability[dim] = sc

        if stability != (new_profile.get("stability_counter") or {}):
            new_profile["stability_counter"] = stability
            changed = True

        return new_profile, changed

    def _apply_merge(self, profile_obj, fragment: dict) -> bool:
        profile = {d: getattr(profile_obj, d, None) for d in DIMENSIONS}
        profile["tag_weights"] = getattr(profile_obj, "tag_weights", None)
        profile["stability_counter"] = getattr(profile_obj, "stability_counter", None)
        profile["entries"] = getattr(profile_obj, "entries", None)
        profile = {k: v for k, v in profile.items() if v is not None}

        new_profile, changed = self._apply_merge_in_memory(profile, fragment)

        for k, v in new_profile.items():
            setattr(profile_obj, k, v)

        return changed

    def _merge_in_memory(self, old: dict, fragment: dict) -> tuple[dict, bool]:
        """纯内存合并（兼容旧接口）"""
        return self._apply_merge_in_memory(old, fragment)

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
        except (RuntimeError, ConnectionError, ValueError) as e:
            logger.warning("Audit LLM failed: %s", e)
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
            if k not in ("tag_weights", "stability_counter", "entries", "last_audit_msg_index", "last_extracted_msg_index")
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

        entries = profile.get("entries") or {}

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

    def _parse_extract_result(self, text: str) -> dict:
        from app.utils.json_parser import parse_llm_json

        data = parse_llm_json(text, fallback={})
        if not isinstance(data, dict):
            data = {}
        updates = data.get("updates", data)
        return {k: v for k, v in updates.items() if k in DIMENSIONS}

    # ── 公开方法：供 tutor/unified chat 后台调用 ───────────────────

    async def extract_and_merge(
        self, profile_dict: dict, messages: list[dict],
    ) -> dict:
        """后台增量画像提取 + 合并。profile_dict 由 Java 传入，纯内存计算。

        Returns:
            {"changed": bool, "profile": dict}
        """
        if not messages:
            return {"changed": False, "profile": profile_dict}

        current_profile = dict(profile_dict) if profile_dict else {}
        last_idx = current_profile.get("last_extracted_msg_index") or 0

        state: ProfileState = {
            "messages": messages,
            "current_profile": current_profile,
            "last_extracted_msg_index": last_idx,
        }

        extract_result = await self._extract_node(state)
        fragment = extract_result.get("extracted_fragment", {})
        if not fragment:
            return {"changed": False, "profile": current_profile}

        judge_state: ProfileState = {
            "messages": messages,
            "current_profile": current_profile,
            "extracted_fragment": fragment,
        }
        judge_result = await self._semantic_judge_node(judge_state)

        merge_state: ProfileState = {
            "messages": messages,
            "current_profile": current_profile,
            "extracted_fragment": fragment,
            "judge_result": judge_result.get("judge_result", {}),
            "last_extracted_msg_index": extract_result.get("last_extracted_msg_index", last_idx),
        }
        merge_result = await self._merge_node(merge_state)

        profile = merge_result.get("current_profile", current_profile)
        changed = merge_result.get("profile_changed", False)

        if changed:
            logger.info(
                "Background profile update: dimensions=%s",
                [k for k, v in fragment.items() if v],
            )

        return {"changed": changed, "profile": profile}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
