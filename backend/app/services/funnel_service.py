from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from app.domain.family import Member
from app.domain.funnel import ALLOWED_PROPS, RETURN_DAYS, EventKind, FunnelStep
from app.repositories.funnel_repository import FunnelRepository
from app.schemas.funnel import LandingEventRequest, WaitlistRequest


class _DayMemo:
    """Per-process set of keys already handled today; it empties itself when the UTC day turns."""

    def __init__(self) -> None:
        self._day: date | None = None
        self._keys: set[UUID] = set()

    def seen(self, key: UUID, today: date) -> bool:
        if self._day != today:
            self._day, self._keys = today, set()
        return key in self._keys

    def add(self, key: UUID) -> None:
        self._keys.add(key)


class FunnelService:
    """Funnel events and the waitlist. Props are limited to ALLOWED_PROPS, never personal data."""

    _checked_today = _DayMemo()

    def __init__(self, repo: FunnelRepository) -> None:
        self._repo = repo

    async def record_event(
        self,
        kind: EventKind,
        family_id: UUID | None = None,
        member_id: UUID | None = None,
        props: dict[str, Any] | None = None,
    ) -> None:
        props = props or {}
        unknown = props.keys() - ALLOWED_PROPS
        if unknown:
            raise ValueError(f"event props not allowed: {sorted(unknown)}")
        await self._repo.add_event(kind, family_id, member_id, props)

    async def record_landing_view(self, body: LandingEventRequest) -> None:
        props = body.model_dump(exclude={"kind"}, exclude_none=True)
        await self.record_event(EventKind.LANDING_VIEW, props=props)

    async def join_waitlist(self, body: WaitlistRequest) -> None:
        """Same outcome for a new and a repeated email, so the answer reveals nothing."""
        added = await self._repo.add_waitlist(
            body.email, body.family_size, [str(b) for b in body.kids_age_bands], body.locale
        )
        if added:
            props = {
                "family_size": body.family_size,
                "kids_age_bands": [str(b) for b in body.kids_age_bands],
                "locale": body.locale,
            }
            await self.record_event(EventKind.WAITLIST_JOIN, props=props)

    async def note_activity(self, member: Member) -> None:
        """Write member_first_seen, then return_d1 / return_d7 on exactly that UTC calendar day.

        The database is asked once per member and day; the caller marks the memo after commit.
        """
        today = datetime.now(UTC).date()
        if self._checked_today.seen(member.id, today):
            return
        first_day = await self._repo.first_event_day(member.id)
        if first_day is None:
            await self.record_event(EventKind.MEMBER_FIRST_SEEN, member.family_id, member.id)
        elif (kind := RETURN_DAYS.get((today - first_day).days)) is not None:
            await self.record_event(kind, member.family_id, member.id)

    @classmethod
    def mark_checked(cls, member_id: UUID) -> None:
        """Call after the request's transaction committed: a rolled-back check must be retried."""
        cls._checked_today.add(member_id)

    async def report(self, days: int) -> list[FunnelStep]:
        return await self._repo.report(days)
