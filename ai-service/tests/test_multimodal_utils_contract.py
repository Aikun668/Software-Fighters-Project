"""多模态消息构建纯能力归位契约（GUIDE P2 第 3 步 / Task 1）。

背景：`internal_api.py` 内的 `ALLOWED_IMAGE_MIMES` / `_extract_text_from_multimodal` /
`_build_multimodal_message` 是本仓库**唯一**的多模态代码，且**零内部调用** ——
48 个端点无一调用它，`UnifiedChatRequest.images` 字段被声明但从未读取
（`app/api/models.py:113`）。本轮只做「纯函数归位」到 `app/utils/multimodal.py`，
**不接线**（不让 `/api/chat` 真的吃图片）。

之所以先写这个文件：`AI_SERVICE_ARCHITECTURE_GUIDE.md` line 148 明确
「不要在没有契约测试前搬动 SSE、错误响应和安全校验」。这里搬的正是
SSRF 判定 + MIME 白名单两道安全校验，没有契约测试不得动手。

- **Part A（`MM-A*`）**：归位前后的**行为规格**，两个阶段都必须全绿。断言经
  `_builder_under_test()` 取到「当前所在位置」的实现，归位前是旧名、归位后是新模块，
  **断言本身一字不改** —— 它证明的正是「搬家没改行为」。
- **Part B（`MM-B*`）**：归位**本身**的断言。Task 1 时全红，Task 2 后转绿。
"""

import ast
import importlib
from pathlib import Path

import pytest

import internal_api


NEW_MODULE = "app.utils.multimodal"
PUBLIC_NAMES = ("ALLOWED_IMAGE_MIMES", "extract_text_from_multimodal", "build_multimodal_message")
OLD_NAMES = ("_build_multimodal_message", "_extract_text_from_multimodal", "ALLOWED_IMAGE_MIMES")

# 与 `tests/test_sse_shared_facilities_contract.py::TestPartASsrfGuard` 同一组探针，
# 那一组从「SSE 契约」角度锁，本组从「多模态契约」角度锁，两侧交叉印证。
SSRF_PROBES = [
    "http://localhost/a.png",
    "http://127.0.0.1/a.png",
    "http://10.0.0.5/a.png",
    "http://169.254.169.254/latest/meta-data",
    "http://2130706433/a.png",
    "http://0x7f000001/a.png",
    "http://017700000001/a.png",
]


def _require(module_path: str, attr: str):
    """归位前抛出可读的 RED 错误（而不是裸 ImportError）。"""
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise AssertionError(
            f"{module_path} 尚未创建 —— Task 2 未落地（{exc}）"
        ) from exc
    if not hasattr(module, attr):
        raise AssertionError(f"{module_path} 尚无 {attr} —— Task 2 未落地")
    return getattr(module, attr)


def _builder_under_test():
    """取「当前所在位置」的构建函数：优先新模块，未归位时回落旧名。

    这样 Part A 的断言在归位前后完全一致 —— 同一套断言、两份实现，
    只要它持续为绿，就证明了搬迁是行为中性的。
    """
    try:
        module = importlib.import_module(NEW_MODULE)
    except ImportError:
        return internal_api._build_multimodal_message
    # 注意不能用 getattr(mod, name, internal_api._build_...) —— 默认值是急切求值的，
    # 归位后 internal_api 上已无旧名，取值那一刻就会 AttributeError。
    build = getattr(module, "build_multimodal_message", None)
    return build if build is not None else internal_api._build_multimodal_message


def _kept_images(message: dict) -> list[str]:
    """取出被保留的图片 URL；content 退化成字符串时返回空表。"""
    content = message["content"]
    if isinstance(content, str):
        return []
    return [
        part["image_url"]["url"]
        for part in content
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]


# ═══════════════════════════════════════════════════════════════════
# Part A —— 行为规格（归位前后都必须全绿）
# ═══════════════════════════════════════════════════════════════════


class TestPartABuilderBehaviour:

    def test_mm_a01_no_images_returns_plain_text_content(self):
        build = _builder_under_test()
        for images in (None, []):
            assert build("描述", images) == {"role": "user", "content": "描述"}, images

    def test_mm_a02_blank_entries_are_skipped(self):
        build = _builder_under_test()
        assert build("描述", ["", "   ", "\t"]) == {"role": "user", "content": "描述"}

    @pytest.mark.parametrize("blocked", SSRF_PROBES)
    def test_mm_a03_ssrf_targets_are_rejected(self, blocked):
        """内网/环回/云元数据地址一律不进入消息体，且整体退化为纯文本。"""
        build = _builder_under_test()
        message = build("描述", [blocked])
        assert _kept_images(message) == [], blocked
        assert message == {"role": "user", "content": "描述"}

    def test_mm_a04_public_https_image_is_kept(self):
        message = _builder_under_test()("描述", ["https://example.com/a.png"])
        assert _kept_images(message) == ["https://example.com/a.png"]

    @pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp", "image/gif"])
    def test_mm_a05_allowed_data_uri_mimes_are_kept(self, mime):
        uri = f"data:{mime};base64,AAAA"
        assert _kept_images(_builder_under_test()("描述", [uri])) == [uri]

    def test_mm_a05b_svg_data_uri_is_rejected(self):
        build = _builder_under_test()
        assert build("描述", ["data:image/svg+xml;base64,AAAA"]) == {
            "role": "user", "content": "描述",
        }

    def test_mm_a06_bare_base64_is_wrapped_as_jpeg(self):
        message = _builder_under_test()("描述", ["rawbase64payload"])
        assert _kept_images(message) == ["data:image/jpeg;base64,rawbase64payload"]

    def test_mm_a07_all_images_rejected_degrades_to_plain_text(self):
        build = _builder_under_test()
        message = build("描述", ["http://127.0.0.1/a.png", "data:image/svg+xml;base64,AA"])
        assert message == {"role": "user", "content": "描述"}

    def test_mm_a07b_empty_text_with_no_kept_image_yields_empty_string(self):
        message = _builder_under_test()("", ["http://127.0.0.1/a.png"])
        assert message == {"role": "user", "content": ""}

    def test_mm_a08_text_part_precedes_image_parts(self):
        message = _builder_under_test()("描述", ["https://example.com/a.png"])
        assert message == {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述"},
                {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
            ],
        }

    def test_mm_a09_semicolonless_svg_data_uri_is_rejected(self):
        """✅ 缺口已修（P3-C 轮）：不带分号的 SVG data URI 必须被拒绝。

        原实现以 `img.find(";") > 0` 为**前置条件**，`data:image/svg+xml,<svg …>`
        取不到分号 → 整段跳过校验被原样保留。现改为「先取 MIME 再判定」，
        本用例由「锁现状缺口」改写为「锁已修复」。
        """
        build = _builder_under_test()
        payload = "data:image/svg+xml,<svg onload=alert(1)>"
        assert build("描述", [payload]) == {"role": "user", "content": "描述"}

    def test_mm_a09b_non_image_data_uri_is_rejected(self):
        """`data:` 前缀一律进白名单校验（非图片 MIME 也不放行）。"""
        build = _builder_under_test()
        payload = "data:text/html,<script>alert(1)</script>"
        assert build("描述", [payload]) == {"role": "user", "content": "描述"}


# ═══════════════════════════════════════════════════════════════════
# Part B —— 归位本身（Task 1 全红，Task 2 后转绿）
# ═══════════════════════════════════════════════════════════════════


class TestPartBExtraction:

    def test_mm_b01_new_module_exposes_three_public_names(self):
        for name in PUBLIC_NAMES:
            assert _require(NEW_MODULE, name) is not None, name
        for name in ("build_multimodal_message", "extract_text_from_multimodal"):
            assert callable(_require(NEW_MODULE, name)), name
        assert _require(NEW_MODULE, "ALLOWED_IMAGE_MIMES") == {
            "image/jpeg", "image/png", "image/webp", "image/gif",
        }

    def test_mm_b02_new_module_reproduces_locked_behaviour(self):
        """新模块逐条重放 Part A 的输入，与**字面期望值**完全相等。

        期望值是从归位前的实现实测抄录的，不引用任何一侧实现 ——
        否则本用例会退化成「自己等于自己」。
        """
        build = _require(NEW_MODULE, "build_multimodal_message")
        image_part = lambda url: {"type": "image_url", "image_url": {"url": url}}
        text_part = {"type": "text", "text": "描述"}

        expected = [
            (("描述", None), {"role": "user", "content": "描述"}),
            (("描述", []), {"role": "user", "content": "描述"}),
            (("", ["http://127.0.0.1/a.png"]), {"role": "user", "content": ""}),
            (("描述", [""]), {"role": "user", "content": "描述"}),
            (
                ("描述", ["https://example.com/a.png"]),
                {"role": "user", "content": [text_part, image_part("https://example.com/a.png")]},
            ),
            (
                ("描述", ["data:image/png;base64,AAAA"]),
                {"role": "user", "content": [text_part, image_part("data:image/png;base64,AAAA")]},
            ),
            (
                ("描述", ["data:image/svg+xml;base64,AAAA"]),
                {"role": "user", "content": "描述"},
            ),
            (
                ("描述", ["rawbase64payload"]),
                {"role": "user", "content": [text_part, image_part("data:image/jpeg;base64,rawbase64payload")]},
            ),
            (("描述", SSRF_PROBES), {"role": "user", "content": "描述"}),
        ]
        for args, want in expected:
            assert build(*args) == want, args

    def test_mm_b03_old_names_are_gone_from_internal_api(self):
        """归位完成锁：旧名必须消失，不允许「两处并存」。"""
        still_there = [name for name in OLD_NAMES if hasattr(internal_api, name)]
        assert still_there == [], f"旧名仍在 internal_api：{still_there}"

    def test_mm_b04_extract_text_from_multimodal_shapes(self):
        extract = _require(NEW_MODULE, "extract_text_from_multimodal")
        assert extract("纯文本") == "纯文本"
        assert extract([
            {"type": "text", "text": "第一段"},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
            {"type": "text", "text": "第二段"},
        ]) == "第一段 第二段"
        assert extract([{"type": "image_url", "image_url": {"url": "x"}}]) == ""
        assert extract([{}, "裸串", 5, None]) == ""
        assert extract(None) == ""
        assert extract(123) == ""

    def test_mm_b05_new_module_does_not_import_internal_api(self):
        """纯能力模块不得反向依赖 API 入口模块。"""
        module = importlib.import_module(NEW_MODULE)
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        offenders = [name for name in imported if name.split(".")[0] == "internal_api"]
        assert offenders == [], f"{NEW_MODULE} 反向依赖 internal_api：{offenders}"
