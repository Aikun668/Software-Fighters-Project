import logging
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    audio_bytes: bytes
    duration_seconds: float
    format: str = "mp3"


class TTSAdapter(Protocol):
    async def generate(self, text: str, voice: str = "alloy") -> TTSResult: ...
    async def test_connectivity(self) -> bool: ...


class OpenAITTSAdapter:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = os.getenv("OPENAI_TTS_MODEL", "tts-1")

    async def generate(self, text: str, voice: str = "alloy") -> TTSResult:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not configured")

        if not text.strip():
            raise ValueError("TTS text cannot be empty")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice,
            "response_format": "mp3",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/audio/speech",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                audio_bytes = resp.content
                duration_estimate = len(text) / 4.5
                return TTSResult(
                    audio_bytes=audio_bytes,
                    duration_seconds=duration_estimate,
                    format="mp3",
                )
        except Exception as e:
            logger.error(f"OpenAI TTS generation failed: {e}")
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


class MockTTSAdapter:
    async def generate(self, text: str, voice: str = "alloy") -> TTSResult:
        logger.info(f"MockTTSAdapter.generate called with text: {text[:50]}...")
        duration_estimate = len(text) / 4.5
        dummy_mp3 = b"\xff\xfb" + b"\x00" * 418
        return TTSResult(
            audio_bytes=dummy_mp3,
            duration_seconds=duration_estimate,
            format="mp3",
        )

    async def test_connectivity(self) -> bool:
        return True


TTS_ADAPTERS: dict[str, type[TTSAdapter]] = {
    "openai": OpenAITTSAdapter,
    "mock": MockTTSAdapter,
}


def get_tts_adapter(adapter_name: str | None = None) -> TTSAdapter:
    name = adapter_name or os.getenv("TTS_ADAPTER", "mock")
    adapter_cls = TTS_ADAPTERS.get(name, MockTTSAdapter)
    return adapter_cls()


async def generate_speech(text: str, voice: str = "alloy", adapter_name: str | None = None) -> TTSResult:
    adapter = get_tts_adapter(adapter_name)
    return await adapter.generate(text, voice)