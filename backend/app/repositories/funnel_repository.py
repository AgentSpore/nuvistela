import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.funnel import FUNNEL_STEPS, EventKind, FunnelStep


class FunnelRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add_waitlist(
        self, email: str, family_size: int, kids_age_bands: list[str], locale: str
    ) -> bool:
        """Insert; False when the email is already on the list."""
        result = await self._conn.execute(
            text(
                "INSERT INTO waitlist (email, family_size, kids_age_bands, locale)"
                " VALUES (:email, :size, :bands, :locale) ON CONFLICT (email) DO NOTHING"
            ),
            {"email": email, "size": family_size, "bands": kids_age_bands, "locale": locale},
        )
        return result.rowcount == 1

    async def add_event(
        self, kind: EventKind, family_id: UUID | None, member_id: UUID | None, props: dict[str, Any]
    ) -> None:
        """Insert; a once-per-member kind that already exists is skipped silently."""
        await self._conn.execute(
            text(
                "INSERT INTO events (family_id, member_id, kind, props)"
                " VALUES (:family_id, :member_id, :kind, CAST(:props AS jsonb))"
                " ON CONFLICT DO NOTHING"
            ),
            {
                "family_id": family_id,
                "member_id": member_id,
                "kind": kind.value,
                "props": json.dumps(props),
            },
        )

    async def first_event_day(self, member_id: UUID) -> date | None:
        """UTC calendar day of the member's first event, None when there is none."""
        return (
            await self._conn.execute(
                text("SELECT (min(at) AT TIME ZONE 'UTC')::date FROM events WHERE member_id = :m"),
                {"m": member_id},
            )
        ).scalar_one()

    async def _returned_families(self, days: int) -> dict[str, int]:
        """Distinct families created in the window with a return event, per return kind."""
        rows = await self._conn.execute(
            text(
                "SELECT r.kind, count(DISTINCT r.family_id) AS n FROM events r"
                " WHERE r.kind IN ('return_d1', 'return_d7')"
                " AND EXISTS (SELECT 1 FROM events c WHERE c.family_id = r.family_id"
                " AND c.kind = 'family_created'"
                " AND c.at >= now() - make_interval(days => :days))"
                " GROUP BY r.kind"
            ),
            {"days": days},
        )
        return {row.kind: row.n for row in rows}

    async def report(self, days: int) -> list[FunnelStep]:
        rows = await self._conn.execute(
            text(
                "SELECT kind, count(*) AS n FROM events"
                " WHERE at >= now() - make_interval(days => :days) GROUP BY kind"
            ),
            {"days": days},
        )
        counts = {row.kind: row.n for row in rows}
        counts.update(await self._returned_families(days))
        steps = []
        for kind, base in FUNNEL_STEPS:
            base_n = counts.get(base.value, 0) if base else 0
            n = counts.get(kind.value, 0)
            steps.append(FunnelStep(kind, n, n / base_n if base_n else None))
        return steps
