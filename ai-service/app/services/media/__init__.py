import base64
import logging
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    url: str = ""
    base64_data: str = ""
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0


class ImageAdapter(Protocol):
    async def generate(self, prompt: str, size: str = "1024x1024") -> ImageResult: ...
    async def test_connectivity(self) -> bool: ...


class OpenAIImageAdapter:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")

    async def generate(self, prompt: str, size: str = "1024x1024") -> ImageResult:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "response_format": "url",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/images/generations",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                images = data.get("data", [])
                if images:
                    url = images[0].get("url", "")
                    b64 = images[0].get("b64_json", "")
                    return ImageResult(url=url, base64_data=b64)
                raise RuntimeError("OpenAI returned empty image data")
        except Exception as e:
            logger.error(f"OpenAI image generation failed: {e}")
            raise

    async def test_connectivity(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


class MockImageAdapter:
    async def generate(self, prompt: str, size: str = "1024x1024") -> ImageResult:
        logger.info(f"MockImageAdapter.generate called with prompt: {prompt[:50]}...")
        return ImageResult(
            url=f"https://example.com/mock-image?prompt={base64.b64encode(prompt.encode()).decode()[:20]}",
            mime_type="image/png",
            width=1024,
            height=1024,
        )

    async def test_connectivity(self) -> bool:
        return True


MEDIA_ADAPTERS: dict[str, type[ImageAdapter]] = {
    "openai": OpenAIImageAdapter,
    "mock": MockImageAdapter,
}


def get_image_adapter(adapter_name: str | None = None) -> ImageAdapter:
    name = adapter_name or os.getenv("IMAGE_ADAPTER", "mock")
    adapter_cls = MEDIA_ADAPTERS.get(name, MockImageAdapter)
    return adapter_cls()


async def generate_image(prompt: str, size: str = "1024x1024", adapter_name: str | None = None) -> ImageResult:
    adapter = get_image_adapter(adapter_name)
    return await adapter.generate(prompt, size)