from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncTransaction

from app.domain.errors import RateLimited
from app.schemas.pilot import PilotEvent, ServerShareKind

MAX_EVENTS_PER_SESSION = 60
_STORED = ("event_id", "session_id", "kind", "locale", "source", "intent")


class PilotRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    def savepoint(self) -> AsyncTransaction:
        """A nested transaction: its failure rolls back only the writes made inside it."""
        return self._conn.begin_nested()

    async def add(self, event: PilotEvent, enforce_cap: bool = False) -> bool:
        """Insert once; return False when an event ID has a different normalized payload.

        With `enforce_cap` (public endpoint) events per session are capped; server-side lead
        events are never refused.
        """
        payload = event.model_dump()
        stored = {key: payload[key] for key in _STORED}
        if enforce_cap:
            await self._check_event_cap(event)
        await self._conn.execute(
            text(
                "INSERT INTO pilot_sessions (session_id, source, locale, internal)"
                " VALUES (:session_id, :source, :locale, :internal)"
                " ON CONFLICT DO NOTHING"
            ),
            payload,
        )
        await self._conn.execute(
            text(
                "INSERT INTO pilot_events (event_id, session_id, kind, locale, source, intent)"
                " VALUES (:event_id, :session_id, :kind, :locale, :source, :intent)"
                " ON CONFLICT (event_id) DO NOTHING"
            ),
            stored,
        )
        row = (
            (
                await self._conn.execute(
                    text(
                        "SELECT event_id, session_id, kind, locale, source, intent"
                        " FROM pilot_events WHERE event_id = :event_id"
                    ),
                    stored,
                )
            )
            .mappings()
            .one()
        )
        return dict(row) == stored

    async def add_share_event(self, kind: ServerShareKind) -> None:
        """Server-side share event: no session, locale, token or share id."""
        await self._conn.execute(
            text(
                "INSERT INTO pilot_events (event_id, kind, source)"
                " VALUES (gen_random_uuid(), :kind, 'share')"
            ),
            {"kind": kind},
        )

    async def share_funnel(self, days: int) -> dict[str, int]:
        """Window counts: links made; sessions that opened, clicked, became a source=share lead."""
        row = (
            (
                await self._conn.execute(
                    text(
                        "SELECT"
                        " count(*) FILTER (WHERE kind = 'share_created') AS created,"
                        " count(DISTINCT session_id) FILTER (WHERE kind = 'share_viewed')"
                        " AS viewed,"
                        " count(DISTINCT session_id) FILTER (WHERE kind = 'share_cta')"
                        " AS cta,"
                        " count(DISTINCT session_id)"
                        " FILTER (WHERE kind = 'lead_created' AND source = 'share')"
                        " AS leads"
                        " FROM pilot_events WHERE at >= now() - make_interval(days => :days)"
                        " AND (session_id IS NULL OR NOT EXISTS (SELECT 1 FROM pilot_sessions s"
                        " WHERE s.session_id = pilot_events.session_id AND s.internal))"
                    ),
                    {"days": days},
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    async def _check_event_cap(self, event: PilotEvent) -> None:
        # Serialize count-then-insert per session so parallel posts cannot overshoot the cap.
        await self._conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:session_id))"),
            {"session_id": str(event.session_id)},
        )
        counts = await self._conn.execute(
            text(
                "SELECT count(*) AS total, count(*) FILTER (WHERE event_id = :event_id) AS same"
                " FROM pilot_events WHERE session_id = :session_id"
            ),
            {"session_id": event.session_id, "event_id": event.event_id},
        )
        total, same = counts.one()
        if total >= MAX_EVENTS_PER_SESSION and not same:
            raise RateLimited("too many events for this pilot session")

    async def report(self, days: int, include_internal: bool = False) -> list[dict]:
        """Count session stages for cohorts selected by their first server receipt.

        Sessions flagged internal (own checks) are left out unless `include_internal`.
        """
        rows = await self._conn.execute(
            text("""
            WITH sessions AS (
                SELECT s.session_id, s.source, s.locale,
                    min(e.at) FILTER (WHERE e.kind = 'landing_view') AS landing,
                    min(e.at) FILTER (WHERE e.kind = 'demo_start') AS demo_start,
                    min(e.at) FILTER (WHERE e.kind = 'demo_complete') AS demo_complete,
                    min(e.at) FILTER (WHERE e.kind = 'cta_click') AS cta,
                    min(e.at) FILTER (WHERE e.kind = 'share_click') AS share,
                    min(e.at) FILTER (WHERE e.kind = 'lead_created') AS lead,
                    bool_or(e.intent = 'solo') AS solo,
                    bool_or(e.intent = 'family') AS family
                FROM pilot_sessions s LEFT JOIN pilot_events e USING (session_id)
                WHERE s.created_at >= now() - make_interval(days => :days)
                    AND (:include_internal OR NOT s.internal)
                GROUP BY s.session_id
                HAVING bool_or(e.kind IS NULL OR e.kind NOT IN ('share_viewed', 'share_cta'))
            )
            SELECT source, locale, count(*) AS sessions,
                count(*) FILTER (WHERE landing IS NOT NULL) AS landing,
                count(*) FILTER (WHERE landing IS NULL) AS missing_landing,
                count(*) FILTER (WHERE landing IS NOT NULL
                    AND demo_start IS NOT NULL) AS demo_start,
                count(*) FILTER (WHERE landing IS NOT NULL
                    AND demo_complete IS NOT NULL) AS demo_complete,
                count(*) FILTER (WHERE landing IS NOT NULL AND cta IS NOT NULL) AS cta,
                count(*) FILTER (WHERE landing IS NOT NULL AND share IS NOT NULL) AS share,
                count(*) FILTER (WHERE landing IS NOT NULL AND lead IS NOT NULL) AS lead,
                count(*) FILTER (WHERE solo) AS solo,
                count(*) FILTER (WHERE family) AS family,
                count(*) FILTER (WHERE
                    (demo_start IS NOT NULL AND (landing IS NULL OR demo_start < landing)) OR
                    (demo_complete IS NOT NULL
                        AND (demo_start IS NULL OR demo_complete < demo_start)) OR
                    (cta IS NOT NULL AND (landing IS NULL OR cta < landing)) OR
                    (share IS NOT NULL AND (landing IS NULL OR share < landing)) OR
                    (lead IS NOT NULL AND (landing IS NULL OR lead < landing
                        OR lead < cta))
                ) AS unordered
            FROM sessions GROUP BY source, locale ORDER BY source, locale
        """),
            {"days": days, "include_internal": include_internal},
        )
        return [dict(row) for row in rows.mappings()]
