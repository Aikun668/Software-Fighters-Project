"""多模态消息构建纯能力

从 `internal_api.py` 原样搬来的两个纯函数与一个白名单常量，行内逻辑一字未改。
搬动前它们在 API 入口模块里**零调用** —— 48 个端点无一使用，
`UnifiedChatRequest.images` 字段被声明但从未读取。

⚠️ 本次只做归位，**没有接线**：`/api/chat` 仍然不会把 `body.images` 喂进来。
接线会让聊天链路真实接受外部图片，属于独立一步，须先处理下方登记的缺口。

⚠️ 已登记缺口：MIME 白名单的判定条件是 `img.find(";") > 0`。不带分号的
data URI（`data:image/svg+xml,<svg …>`）取不到分号，整段判定被跳过，SVG 因此
绕过白名单。当前零调用故未暴露，接线后即为活风险。归位不改行为，缺口保留原样。
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
        if img.startswith("data:image/"):
            mime_end = img.find(";")
            if mime_end > 0:
                mime = img[len("data:"):mime_end]
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
