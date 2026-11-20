from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.channels.push.rules import QuestWaiting
from app.channels.push.sender import PushSubscription
from app.domain.errors import Conflict
from app.domain.family import Member

MAX_PER_MEMBER = 5
_HAS_TARGET = {  # a Telegram reminder needs a time zone, which only a push subscription holds
    "push": "EXISTS (SELECT 1 FROM push_subscriptions p WHERE p.family_id = f.id)",
    "telegram": "EXISTS (SELECT 1 FROM tg_chats t WHERE t.family_id = f.id AND t.notify)"
    " AND EXISTS (SELECT 1 FROM push_subscriptions p WHERE p.family_id = f.id)",
}


class PushRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert(self, member: Member, endpoint: str, p256dh: str, auth: str, tz: str) -> None:
        """One row per endpoint. A device used by another adult of the same family moves to the
        new member; another family's row is never taken over (Conflict). Re-subscribing renews
        created_at, so an active device is not the one evicted. A member keeps at most
        MAX_PER_MEMBER devices: oldest go (two parallel inserts may briefly leave one more)."""
        row = await self._conn.execute(
            text(
                "INSERT INTO push_subscriptions (member_id, family_id, endpoint, p256dh, auth, tz)"
                " VALUES (:mid, :fid, :endpoint, :p256dh, :auth, :tz)"
                " ON CONFLICT (endpoint) DO UPDATE SET member_id = :mid, family_id = :fid,"
                " p256dh = :p256dh, auth = :auth, tz = :tz,"
                " created_at = now()"
                " WHERE push_subscriptions.family_id = :fid RETURNING id"
            ),
            {
                "mid": member.id, "fid": member.family_id, "endpoint": endpoint,
                "p256dh": p256dh, "auth": auth, "tz": tz,
            },
        )  # fmt: skip
        if row.first() is None:
            raise Conflict("this device is registered by another family")
        await self._conn.execute(
            text(
                "DELETE FROM push_subscriptions WHERE id IN (SELECT id FROM push_subscriptions"
                " WHERE member_id = :mid ORDER BY created_at DESC, id OFFSET :keep)"
            ),
            {"mid": member.id, "keep": MAX_PER_MEMBER},
        )

    async def delete_own(self, member_id: UUID, endpoint: str) -> None:
        await self._conn.execute(
            text("DELETE FROM push_subscriptions WHERE member_id = :mid AND endpoint = :endpoint"),
            {"mid": member_id, "endpoint": endpoint},
        )

    async def delete_ids(self, ids: list[UUID]) -> None:
        await self._conn.execute(
            text("DELETE FROM push_subscriptions WHERE id = ANY(:ids)"), {"ids": ids}
        )

    async def family_subscriptions(self, family_id: UUID) -> list[PushSubscription]:
        """Newest first: the first one's time zone stands for the family."""
        rows = await self._conn.execute(
            text(
                "SELECT id, tz, endpoint, p256dh, auth FROM push_subscriptions"
                " WHERE family_id = :fid ORDER BY created_at DESC, id"
            ),
            {"fid": family_id},
        )
        return [PushSubscription(*row) for row in rows]

    async def family_locale(self, family_id: UUID) -> str | None:
        row = await self._conn.execute(
            text("SELECT locale FROM families WHERE id = :fid"), {"fid": family_id}
        )
        return row.scalar_one_or_none()

    async def last_adventure_poll(self, family_id: UUID) -> datetime | None:
        """When a client last polled the adventure screen (the tab is open while it is recent)."""
        row = await self._conn.execute(
            text("SELECT last_adventure_poll_at FROM families WHERE id = :fid"), {"fid": family_id}
        )
        return row.scalar_one_or_none()

    async def quest_waiting_candidates(
        self, older_than: datetime, channel: str = "push"
    ) -> list[QuestWaiting]:
        rows = await self._conn.execute(
            text(
                "SELECT f.id, f.locale, q.title, q.created_at, f.last_adventure_poll_at,"
                " s.last_sent_at, coalesce(s.unanswered, 0)"
                " FROM quests q JOIN families f ON f.id = q.family_id"
                " LEFT JOIN reminder_state s ON s.family_id = f.id AND s.channel = :channel"
                " WHERE q.status = 'open' AND q.created_at <= :cutoff AND " + _HAS_TARGET[channel]
            ),
            {"cutoff": older_than, "channel": channel},
        )
        return [QuestWaiting(*row) for row in rows]

    async def release_unanswered(self, family_id: UUID, channel: str) -> None:
        """A send nobody received must not count toward the silence-after-N rule."""
        await self._conn.execute(
            text(
                "UPDATE reminder_state SET unanswered = greatest(unanswered - 1, 0)"
                " WHERE family_id = :fid AND channel = :channel"
            ),
            {"fid": family_id, "channel": channel},
        )

    async def claim_send(
        self, family_id: UUID, channel: str, at: datetime, unanswered: int, seen: datetime | None
    ) -> bool:
        """Record a send; False when another process recorded one since `seen` (send once)."""
        result = await self._conn.execute(
            text(
                "INSERT INTO reminder_state (family_id, channel, last_sent_at, unanswered)"
                " VALUES (:fid, :channel, :at, :n)"
                " ON CONFLICT (family_id, channel)"
                " DO UPDATE SET last_sent_at = :at, unanswered = :n"
                " WHERE reminder_state.last_sent_at IS NOT DISTINCT FROM :seen"
            ),
            {"fid": family_id, "channel": channel, "at": at, "n": unanswered, "seen": seen},
        )
        return result.rowcount == 1
