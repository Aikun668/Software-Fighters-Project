import asyncio
import logging
from typing import AsyncIterator, Iterator

from app.agents.profile_agent import ProfileAgent
from app.agents.tutor_agent import TutorAgent
from app.events.types import (
    StreamEvent,
    error_content_event,
    flat_done_event,
    token_event,
)

logger = logging.getLogger(__name__)

TUTOR_FAILED_MESSAGE = "答疑失败，请稍后重试"


def _chunks(text: str, size: int) -> Iterator[str]:
    """按固定字数切分文本，与 API 现状的 _sse_stream_chunks 同规则。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


class TutorCenter:
    def __init__(
        self,
        tutor_agent: TutorAgent | None = None,
        profile_agent: ProfileAgent | None = None,
    ):
        self.tutor_agent = tutor_agent
        self.profile_agent = profile_agent
        # 节流节奏：API 现状 0.03s 间隔 / 4 字分片，离线测试注入 0
        self.token_delay = 0.03
        self.chunk_size = 4

    def _tutor_agent(self) -> TutorAgent:
        if self.tutor_agent is None:
            self.tutor_agent = TutorAgent()
        return self.tutor_agent

    def _profile_agent_instance(self) -> ProfileAgent:
        if self.profile_agent is None:
            self.profile_agent = ProfileAgent()
        return self.profile_agent

    async def stream_chat(
        self,
        *,
        messages: list[dict],
        student_profile: dict,
    ) -> AsyncIterator[StreamEvent]:
        """答疑业务事件流：token* → done（含 domain，可选 profile_delta）。

        - 正文按 chunk_size 分片，逐片 token 事件（节流 token_delay）
        - 正文为空时不产 token，直接 done
        - 画像提取仅在正文与 messages 均非空时触发；异常静默降级
        - 任何异常 → error + done，恰好一个 done 收尾
        """
        try:
            state = await self._tutor_agent().run({
                "messages": messages,
                "student_profile": student_profile,
            })
            response = state.get("response", "")
            domain = state.get("domain", "")

            if response:
                for chunk in _chunks(response, self.chunk_size):
                    await asyncio.sleep(self.token_delay)
                    yield token_event(chunk)

            profile_delta = None
            if response and messages:
                try:
                    result = await self._profile_agent_instance().extract_and_merge(
                        student_profile, messages,
                    )
                    if result.get("changed"):
                        profile_delta = result.get("profile")
                        logger.info("Background profile updated during tutor chat")
                except Exception as exc:
                    logger.warning("Background profile extract failed: %s", exc)

            done_payload: dict = {"domain": domain}
            if profile_delta:
                done_payload["profile_delta"] = profile_delta
            yield flat_done_event(done_payload)
        except Exception as e:
            logger.error(f"Tutor chat stream failed: {e}")
            yield error_content_event(TUTOR_FAILED_MESSAGE)
            yield flat_done_event()
