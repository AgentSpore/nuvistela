"""Conversation persistence seam. K2 implements it over the `agent_messages` table."""

from collections.abc import Sequence
from typing import Protocol

from pydantic_ai.messages import ModelMessage

from app.agent.models import AgentEvent


class ConversationStore(Protocol):
    """Per-family message history. Implementations must use the SDK message serialization."""

    async def load(self, family_id: str, limit: int) -> list[ModelMessage]:
        """Return at most `limit` newest messages, oldest first; empty for a new family.

        A plain tail slice is acceptable: the runtime drops any leading messages that would
        split a tool call from its result before sending the history to the model.
        """
        ...

    async def append(self, event: AgentEvent, messages: Sequence[ModelMessage]) -> None:
        """Persist the messages produced by one successful turn of `event`."""
        ...
