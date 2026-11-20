from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class LinkedChat:
    family_id: UUID
    notify: bool
    locale: str


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
                " ON CONFLICT (chat_id) DO UPDATE SET family_id = EXCLUDED.family_id,"
                " notify = tg_chats.notify AND tg_chats.family_id = EXCLUDED.family_id"
            ),
            {"c": chat_id, "f": family_id},
        )

    async def linked_chat(self, chat_id: int) -> LinkedChat | None:
        row = (
            await self._conn.execute(
                text(
                    "SELECT c.family_id, c.notify, f.locale FROM tg_chats c"
                    " JOIN families f ON f.id = c.family_id WHERE c.chat_id = :c"
                ),
                {"c": chat_id},
            )
        ).first()
        return LinkedChat(row.family_id, row.notify, row.locale) if row else None

    async def set_notify(self, chat_ids: list[int], on: bool) -> None:
        await self._conn.execute(
            text("UPDATE tg_chats SET notify = :on WHERE chat_id = ANY(:ids)"),
            {"on": on, "ids": chat_ids},
        )

    async def notify_chats(self, family_id: UUID) -> list[int]:
        rows = await self._conn.execute(
            text("SELECT chat_id FROM tg_chats WHERE family_id = :f AND notify ORDER BY chat_id"),
            {"f": family_id},
        )
        return [r.chat_id for r in rows]
