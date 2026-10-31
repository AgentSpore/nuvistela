"""ConversationStore over `agent_messages`, bound to the request's transaction."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.agent.models import AgentEvent

_INSERT = text(
    "INSERT INTO agent_messages (family_id, member_id, role, channel, content, created_at)"
    " VALUES (CAST(:family_id AS uuid), CAST(:member_id AS uuid), :role, :channel,"
    " CAST(:content AS jsonb), :created_at)"
)
_LOAD = text(
    "SELECT content FROM agent_messages WHERE family_id = CAST(:family_id AS uuid)"
    " ORDER BY created_at DESC, id DESC LIMIT :limit"
)


class PostgresConversationStore:
    """Per-family history; commit and rollback belong to the connection's owner."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def load(self, family_id: str, limit: int) -> list[ModelMessage]:
        rows = await self._conn.execute(_LOAD, {"family_id": family_id, "limit": limit})
        newest_first = [row.content for row in rows]
        return ModelMessagesTypeAdapter.validate_python(list(reversed(newest_first)))

    async def append(self, event: AgentEvent, messages: Sequence[ModelMessage]) -> None:
        if not messages:
            return
        # now() is the transaction start, so every row of a turn would tie; spread by 1 us.
        start = datetime.now(UTC)
        dumped = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
        await self._conn.execute(
            _INSERT,
            [
                {
                    "family_id": event.family_id,
                    "member_id": event.member_id if isinstance(m, ModelRequest) else None,
                    "role": "user" if isinstance(m, ModelRequest) else "agent",
                    "channel": event.channel,
                    "content": json.dumps(content),
                    "created_at": start + timedelta(microseconds=i),
                }
                for i, (m, content) in enumerate(zip(messages, dumped, strict=True))
            ],
        )
