"""Streaming progress event system for multi-agent workflows.

Design:
  Each workflow node pushes structured StreamEvent objects into a shared
  asyncio.Queue. The SSE endpoint reads from the queue and serializes events
  to JSON lines for the frontend.

  Coarse-grained approach — ~10 events per resource generation cycle:
    plan_start -> plan_done -> agent_start -> agent_done -> ... -> done
"""

from app.events.types import StreamEventType, StreamEvent

__all__ = ["StreamEventType", "StreamEvent"]
