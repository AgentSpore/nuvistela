from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class LinkRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create_code(self, member_id: UUID, code_hash: str, expires_at: datetime) -> None:
        """One live code per member: older ones (and any expired) are dropped first."""
        await self._conn.execute(
            text("DELETE FROM link_codes WHERE member_id = :m OR expires_at <= now()"),
            {"m": member_id},
        )
        await self._conn.execute(
            text("INSERT INTO link_codes (code_hash, member_id, expires_at) VALUES (:h, :m, :e)"),
            {"h": code_hash, "m": member_id, "e": expires_at},
        )

    async def consume_code(self, code_hash: str) -> UUID | None:
        """Delete a live code and return its family; None if unknown, used or expired.

        A concurrent second DELETE of the same row waits on the lock, then matches nothing.
        """
        row = (
            await self._conn.execute(
                text(
                    "WITH used AS (DELETE FROM link_codes WHERE code_hash = :h"
                    " AND expires_at > now() RETURNING member_id)"
                    " SELECT m.family_id FROM used JOIN members m ON m.id = used.member_id"
                ),
                {"h": code_hash},
            )
        ).first()
        return row.family_id if row else None

    async def bind_chat(self, chat_id: int, family_id: UUID) -> None:
        await self._conn.execute(
            text(
                "INSERT INTO tg_chats (chat_id, family_id) VALUES (:c, :f)"
                " ON CONFLICT (chat_id) DO UPDATE SET family_id = EXCLUDED.family_id"
            ),
            {"c": chat_id, "f": family_id},
        )

    async def family_of_chat(self, chat_id: int) -> UUID | None:
        row = (
            await self._conn.execute(
                text("SELECT family_id FROM tg_chats WHERE chat_id = :c"), {"c": chat_id}
            )
        ).first()
        return row.family_id if row else None
