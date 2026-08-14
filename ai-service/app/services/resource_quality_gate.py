"""资源质量门控 — 确定性 Validator 与轻量 Judge 契约。

职责：
  - ValidationResult / ReviewDecision 是不可变结果类型。
  - ResourceValidator 不调用 LLM，只做确定性结构校验。
  - 首版仅覆盖 content 与 interactive_diagram 两类资源，其余类型放行。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)


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
            valid = any(
                block.get("type") == "interactive_diagram"
                and bool(str(block.get("content", "")).strip())
                for block in content_blocks
            )
            return ValidationResult(valid, "" if valid else "缺少 interactive_diagram 内容块")
        return ValidationResult(True)
