"""多模态消息构建纯能力

从 `internal_api.py` 原样搬来的两个纯函数与一个白名单常量，行内逻辑一字未改。
搬动前它们在 API 入口模块里**零调用** —— 48 个端点无一使用，
`UnifiedChatRequest.images` 字段被声明但从未读取。

⚠️ 本次只做归位，**没有接线**：`/api/chat` 仍然不会把 `body.images` 喂进来。
接线会让聊天链路真实接受外部图片，属于独立一步，须先处理下方登记的缺口。

✅ 已修缺口（P3-C 轮）：MIME 白名单原先以 `img.find(";") > 0` 为前置条件，
不带分号的 data URI（`data:image/svg+xml,<svg …>`）会整段跳过校验 → SVG 绕过白名单。
现改为「先取 MIME 再判定」，且 `data:` 前缀一律进校验。契约用例
`MM-A09` 已从「锁现状缺口」改写为「锁已修复」，由 `MM-A09b` 锁其他非图片 MIME。
"""

import logging

from app.utils.security_middleware import is_internal_url

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def extract_text_from_multimodal(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(parts)
    return ""


def build_multimodal_message(text: str, images: list[str] | None) -> dict:
    if not images:
        return {"role": "user", "content": text}

    content_parts: list[dict] = []
    if text:
        content_parts.append({"type": "text", "text": text})

    for img in images:
        if not img or not img.strip():
            continue
        if img.startswith("data:"):
            # MIME 必须先取再判，**不能**把 `find(";")` 当前置条件：不带分号的
            # data URI（`data:image/svg+xml,<svg …>`）取不到分号，会整段跳过校验
            # → SVG 绕过白名单（历轮登记的 MM-A09，本轮已修）。
            mime = img[len("data:"):].split(";", 1)[0].split(",", 1)[0].strip().lower()
            if mime not in ALLOWED_IMAGE_MIMES:
                logger.warning(f"Rejected image with unsupported MIME: {mime}")
                continue
            url = img
        elif img.startswith("http://") or img.startswith("https://"):
            if is_internal_url(img):
                logger.warning(f"Rejected internal/infra URL for SSRF prevention: {img[:80]}")
                continue
            url = img
        else:
            url = f"data:image/jpeg;base64,{img}"
        content_parts.append({"type": "image_url", "image_url": {"url": url}})

    if not content_parts:
        return {"role": "user", "content": text}
    if len(content_parts) == 1 and content_parts[0].get("type") == "text":
        return {"role": "user", "content": text}
    return {"role": "user", "content": content_parts}
