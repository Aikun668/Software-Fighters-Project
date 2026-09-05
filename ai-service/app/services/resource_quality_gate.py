"""资源质量门控 — 确定性 Validator 与轻量 LLM Judge。

职责：
  - ValidationResult / ReviewDecision 是不可变结果类型。
  - ResourceValidator 不调用 LLM，只做确定性结构校验。
  - ResourceReviewService 是轻量 LLM-as-Judge，只输出 pass | repair | skipped。
  - 首版仅覆盖 content 与 interactive_diagram 两类资源，其余类型放行/跳过。
"""

from dataclasses import dataclass, field
from typing import Literal

from app.services.diagram_schema import validate_diagram_schema
from app.services.llm_service import create_llm, PROFILE_REVIEW
from app.utils.json_parser import parse_llm_json
from app.utils.prompt_loader import build_prompt, interpolate_variables


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewDecision:
    status: Literal["pass", "repair", "skipped"]
    reason: str = ""
    fixes: list[str] = field(default_factory=list)


class ResourceValidator:
    def validate(self, resource_type: str, content_blocks: list[dict]) -> ValidationResult:
        if not content_blocks:
            return ValidationResult(False, "content_blocks 不能为空", ["content_blocks 不能为空"])
        if resource_type == "content":
            valid = any(
                block.get("type") == "section"
                and bool(str(block.get("heading", "")).strip())
                and bool(str(block.get("content", "")).strip())
                for block in content_blocks
            )
            return ValidationResult(valid, "" if valid else "缺少完整 section 内容块")
        if resource_type == "interactive_diagram":
            for block in content_blocks:
                if not isinstance(block, dict) or block.get("type") != "interactive_diagram":
                    continue
                issues = validate_diagram_schema(block.get("diagram"))
                if issues:
                    return ValidationResult(False, "; ".join(issues), issues)
                return ValidationResult(True)
            return ValidationResult(False, "缺少 interactive_diagram 内容块")
        return ValidationResult(True)


def _format_diagram_for_judge(content_blocks) -> str:
    """把图解 block 转成可读的节点/边描述，供 Judge 评审（不评审 HTML）。"""
    for block in content_blocks or []:
        if isinstance(block, dict) and block.get("type") == "interactive_diagram":
            diagram = block.get("diagram") or {}
            lines = []
            if diagram.get("title"):
                lines.append(f"标题：{diagram.get('title')}")
            if diagram.get("summary"):
                lines.append(f"概述：{diagram.get('summary')}")
            nodes = diagram.get("nodes", [])
            lines.append("节点：" + "；".join(
                f"{n.get('label', '')}（{n.get('detail', '')}）"
                for n in nodes if isinstance(n, dict)
            ))
            edges = diagram.get("edges", [])
            lines.append("关系：" + "；".join(
                f"{e.get('source', '')}→{e.get('target', '')}（{e.get('label', '')}）"
                for e in edges if isinstance(e, dict)
            ))
            return "\n".join(lines)
    return "（无图解数据）"


_JUDGE_SCOPED_TYPES = frozenset({"content", "interactive_diagram"})

_JUDGE_PROMPT_FILES = {
    "content": "resource_judge.yaml",
    "interactive_diagram": "visualize_judge.yaml",
}


class ResourceReviewService:
    """轻量 LLM-as-Judge：只判断 pass | repair，故障时降级为 skipped。"""

    def __init__(self, use_mock: bool = False, llm=None):
        self.use_mock = use_mock
        self._llm = llm

    def _build_llm(self):
        """从 PROFILE_REVIEW 构建默认 Judge LLM（确定性：temperature=0.0）。"""
        cfg = PROFILE_REVIEW.default
        return create_llm(
            model=cfg.model or None,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            use_mock=self.use_mock,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            thinking_enabled=cfg.thinking_enabled,
        )

    async def review(
        self, topic, resource_type, content_blocks, student_profile
    ) -> ReviewDecision:
        if resource_type not in _JUDGE_SCOPED_TYPES:
            return ReviewDecision("skipped", "该资源类型未启用 Judge")
        try:
            raw = await self._chat(topic, resource_type, content_blocks, student_profile)
            data = parse_llm_json(raw, fallback={})
            if not isinstance(data, dict) or "decision" not in data:
                return ReviewDecision("skipped", "Judge 输出无法解析")
            decision = "repair" if data.get("decision") == "repair" else "pass"
            fixes = [
                str(item) for item in data.get("fixes", [])[:3] if str(item).strip()
            ]
            return ReviewDecision(decision, str(data.get("reason", ""))[:60], fixes)
        except Exception:
            return ReviewDecision("skipped", "Judge 不可用")

    async def _chat(self, topic, resource_type, content_blocks, student_profile) -> str:
        """构建 Judge Prompt 并调用 LLM，返回原始文本。"""
        filename = _JUDGE_PROMPT_FILES[resource_type]
        system_prompt = build_prompt("tutor_agent", filename=filename, key="system")
        user_template = build_prompt("tutor_agent", filename=filename, key="user")
        variables = {"topic": topic, "student_profile": student_profile or {}}
        if resource_type == "interactive_diagram":
            variables["diagram_view"] = _format_diagram_for_judge(content_blocks)
        else:
            variables["content_blocks"] = content_blocks
        user_prompt = interpolate_variables(user_template, variables)
        llm = self._llm if self._llm is not None else self._build_llm()
        messages = [{"role": "user", "content": user_prompt}]
        return await llm.chat(messages, system_prompt=system_prompt)
