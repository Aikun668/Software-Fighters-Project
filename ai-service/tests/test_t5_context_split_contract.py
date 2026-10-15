"""T5 契约：路由层只依赖简要上下文（message + mode），不消费 profile/context。

T5 Gate 1 要求「区分路由需要的简要上下文与业务 Agent 需要的专业上下文」。
本测试把现状钉死：`CapabilityGate.decide` 与 `RouterAgent.decide`（关键词路径）
**不得消费** `student_profile` / `context`——它们的形参是为调用方兼容保留的。

若将来要让路由依赖画像/历史，必须先改本契约（即显式决策），不能悄悄依赖。
"""

import ast
import inspect
import os

from app.centers.router_agent import RouterAgent
from app.services.capability_gate import CapabilityGate

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))


def _decide_body_uses(name: str) -> set[str]:
    """返回指定方法函数体内引用到的标识符名集合（不含签名）。"""
    path = os.path.join(APP_DIR, "services", "capability_gate.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            used = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Name):
                    used.add(n.id)
                elif isinstance(n, ast.Attribute):
                    pass
            return used
    raise AssertionError(f"{name} 未找到")


class TestRoutingLayerUsesBriefContextOnly:
    def test_capability_gate_decide_does_not_use_profile_or_context(self):
        used = _decide_body_uses("decide")
        assert "student_profile" not in used, "CapabilityGate 不应消费 student_profile"
        assert "context" not in used, "CapabilityGate 不应消费 context"

    def test_router_decide_signature_keeps_profile_context_for_compat(self):
        sig = inspect.signature(RouterAgent.decide)
        # 形参保留（兼容既有调用方），但语义上不被消费
        assert "message" in sig.parameters
        assert "mode" in sig.parameters

    def test_router_keyword_candidates_only_takes_message(self):
        sig = inspect.signature(RouterAgent._keyword_candidates)
        assert list(sig.parameters) == ["self", "message"], (
            "关键词候选只应依赖 message；若需 profile/context 必须先改 T5 契约"
        )
