"""T5 契约：Dispatcher 不再持有业务正文合成 / SSE 帧拼装（T5-Gate ②）。

T5 把这些纯函数抽到 `app/centers/chat_presentation.py`，Dispatcher 只调用不持有。
本测试防止它们被搬回 Dispatcher（否则职责又会重新交叉）。

零行为变化由 `test_t5_sse_contract_baseline.py`（契约 --verify）另行保证。
"""

import ast
import os

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
DISPATCHER = os.path.join(APP_DIR, "centers", "chat_task_dispatcher.py")
PRESENTATION = os.path.join(APP_DIR, "centers", "chat_presentation.py")

MOVED = {
    "ensure_user_visible_response",
    "summarize_product",
    "map_event_type",
    "build_run_summary",
    "build_next_steps",
}


def _method_names(path: str) -> set[str]:
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
    return names


class TestDispatcherNoLongerOwnsPresentation:
    def test_dispatcher_does_not_define_moved_methods(self):
        defined = _method_names(DISPATCHER)
        leaked = {f"_{n}" for n in MOVED} & defined
        assert not leaked, f"这些方法应留在 chat_presentation，不该回到 Dispatcher: {leaked}"

    def test_presentation_module_defines_moved_functions(self):
        defined = _method_names(PRESENTATION)
        missing = MOVED - defined
        assert not missing, f"chat_presentation 缺少: {missing}"

    def test_dispatcher_imports_from_presentation(self):
        src = open(DISPATCHER, encoding="utf-8").read()
        assert "from app.centers.chat_presentation import" in src
        # summarize_product 由 presentation 内部（ensure_user_visible_response）调用，
        # Dispatcher 不直接引用它；其余 4 个是 Dispatcher 的直接调用点。
        for n in ("ensure_user_visible_response", "map_event_type",
                  "build_run_summary", "build_next_steps"):
            assert n in src, f"Dispatcher 应调用 chat_presentation.{n}"
