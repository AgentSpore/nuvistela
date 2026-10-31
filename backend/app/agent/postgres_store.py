"""ConversationStore over `agent_messages`, bound to the request's transaction."""

import json
import logging
from collections.abc import Sequence

from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.agent.errors import AgentBusyError
from app.agent.models import AgentEvent

logger = logging.getLogger(__name__)

_INSERT = text(
    "INSERT INTO agent_messages (family_id, member_id, role, channel, content)"
    " VALUES (CAST(:family_id AS uuid), CAST(:member_id AS uuid), :role, :channel,"
    " CAST(:content AS jsonb))"
)
_LOAD = text(
    "SELECT content FROM agent_messages WHERE family_id = CAST(:family_id AS uuid)"
    " ORDER BY seq DESC LIMIT :limit"
)
# One conversation lock per family, released with the transaction. Non-blocking: a waiter
# would sit on a pooled connection, so a busy family is refused instead (AgentBusyError).
_LOCK = text("SELECT pg_try_advisory_xact_lock(hashtextextended(:family_id, 0))")


def _is_user_prompt(message: ModelMessage) -> bool:
    return isinstance(message, ModelRequest) and any(
        isinstance(p, UserPromptPart) for p in message.parts
    )


class PostgresConversationStore:
    """Per-family history; commit and rollback belong to the connection's owner."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def load(self, family_id: str, limit: int) -> list[ModelMessage]:
        """Take the family lock (or raise AgentBusyError); return the newest readable messages."""
        if not (await self._conn.execute(_LOCK, {"family_id": family_id})).scalar_one():
            raise AgentBusyError("a turn is already running for this family")
        rows = await self._conn.execute(_LOAD, {"family_id": family_id, "limit": limit})
        messages: list[ModelMessage] = []
        skipped = 0
        for row in reversed(rows.all()):
            try:
                messages.extend(ModelMessagesTypeAdapter.validate_python([row.content]))
            except ValidationError:  # never log the error: it quotes the stored chat
                skipped += 1
        if skipped:
            logger.warning("skipped %d unreadable history rows, family_id=%s", skipped, family_id)
        return messages

    async def append(self, event: AgentEvent, messages: Sequence[ModelMessage]) -> None:
        if not messages:
            return
        dumped = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
        # Executed in list order, so the identity column `seq` follows the turn's order.
        await self._conn.execute(
            _INSERT,
            [
                {
                    "family_id": event.family_id,
                    "member_id": event.member_id if _is_user_prompt(m) else None,
                    "role": self._role(m),
                    "channel": event.channel,
                    "content": json.dumps(content),
                }
                for m, content in zip(messages, dumped, strict=True)
            ],
        )

    @staticmethod
    def _role(message: ModelMessage) -> str:
        if not isinstance(message, ModelRequest):
            return "agent"
        return "user" if _is_user_prompt(message) else "system"
