"""Conversation persistence seam. K2 implements it over the `agent_messages` table."""

from collections.abc import Sequence
from typing import Protocol

from pydantic_ai.messages import ModelMessage


class ConversationStore(Protocol):
    """Per-family message history. Implementations must use the SDK message serialization."""

    async def load(self, family_id: str) -> list[ModelMessage]:
        """Return the stored history, oldest first; empty for a new family."""
        ...

    async def append(self, family_id: str, messages: Sequence[ModelMessage]) -> None:
        """Persist the messages produced by one successful turn."""
        ...
