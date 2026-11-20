"""Sends reminders over every configured channel: "chapter ready" (queued by the chapter
worker) and "quest waiting"."""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.channels.push.repository import PushRepository
from app.channels.push.rules import QUEST_MIN_AGE, QuestWaiting, quest_waiting_due
from app.channels.push.texts import chapter_ready_text, quest_waiting_text
from app.channels.reminders import Reminder, ReminderChannel
from app.core.config import Settings
from app.domain.funnel import EventKind
from app.repositories.funnel_repository import FunnelRepository
from app.repositories.job_repository import Job, JobRepository
from app.repositories.pilot_repository import PilotRepository
from app.repositories.world_repository import WorldRepository
from app.services.funnel_service import FunnelService
from app.services.pilot_service import PilotService

logger = logging.getLogger(__name__)
TAB_OPEN_WINDOW = timedelta(seconds=15)  # the client polls every ~1.5 s while the tab is shown
TAB_CLOSE_MARGIN = timedelta(seconds=1)
CHAPTER_READY_MAX_AGE = timedelta(minutes=2)  # a late "chapter ready" is worse than none


@dataclass(frozen=True)
class _Delivery:
    channel: ReminderChannel[Any]
    targets: Sequence[Any]
    reminder: Reminder


@dataclass(frozen=True)
class _Defer:
    """The tab looks open: ask again once the poll window has passed."""

    until: datetime


@dataclass(frozen=True)
class _Outcome:
    delivery: _Delivery
    delivered: int
    gone: list[Any]


class ReminderWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        channels: Sequence[ReminderChannel[Any]],
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._engine, self._channels, self._settings, self._clock = (
            engine, channels, settings, clock,
        )  # fmt: skip
        self._hours = range(settings.reminder_window_start_hour, settings.reminder_window_end_hour)

    async def run_notify_once(self) -> bool:
        """Handle one queued "chapter ready" job; False when none is due."""
        async with self._engine.begin() as conn:
            job = await JobRepository(conn).claim(["notify"])
            if job is None:
                return False
            deliveries = await self._chapter_ready(conn, job)
            if isinstance(deliveries, _Defer):
                if not await JobRepository(conn).defer(job, deliveries.until):
                    logger.warning("notify job %s lost its lease before deferring", job.id)
                return True
        outcomes = await self._deliver(deliveries)
        async with self._engine.begin() as conn:
            for outcome in outcomes:
                await self._settle(conn, outcome)
            if not await JobRepository(conn).complete(job):
                logger.warning("notify job %s lost its lease before completing", job.id)
        return True

    async def _chapter_ready(self, conn: AsyncConnection, job: Job) -> list[_Delivery] | _Defer:
        """Nothing when no reminder is due (stale job, no target); a fresh job whose tab looks
        open is deferred past the poll window, as the player may have just left."""
        now = self._clock()
        if now - datetime.fromisoformat(job.payload["ready_at"]) > CHAPTER_READY_MAX_AGE:
            return []
        repo = PushRepository(conn)
        last_poll = await repo.last_adventure_poll(job.family_id)
        if last_poll and last_poll > now - TAB_OPEN_WINDOW:
            return _Defer(last_poll + TAB_OPEN_WINDOW + TAB_CLOSE_MARGIN)
        found = [(ch, await ch.targets(conn, job.family_id)) for ch in self._channels]
        found = [(ch, targets) for ch, targets in found if targets]
        if not found:
            return []
        locale = await repo.family_locale(job.family_id) or "en"
        text = chapter_ready_text(locale, await self._world_title(conn, job.family_id))
        reminder = Reminder(job.family_id, "chapter_ready", locale, text)
        return [_Delivery(ch, targets, reminder) for ch, targets in found]

    async def run_reminders_once(self) -> int:
        """One scan for "quest waiting": returns how many (family, channel) pairs were reminded."""
        now = self._clock()
        sent = 0
        for channel in self._channels:
            async with self._engine.begin() as conn:
                candidates = await channel.candidates(conn, now - QUEST_MIN_AGE)
            for candidate in candidates:
                sent += await self._remind(channel, candidate, now)
        return sent

    async def _remind(self, channel: ReminderChannel[Any], c: QuestWaiting, now: datetime) -> int:
        async with self._engine.begin() as conn:
            repo = PushRepository(conn)
            zone_source = await repo.family_subscriptions(c.family_id)  # newest device's zone
            if not zone_source or not (tz := self._zone(zone_source[0].tz)):
                return 0
            if not quest_waiting_due(c, now, tz, self._hours):
                return 0
            targets = await channel.targets(conn, c.family_id)
            if not targets:
                return 0
            claimed = await repo.claim_send(
                c.family_id, channel.name, now, c.effective_unanswered + 1, c.last_sent_at
            )
            if not claimed:
                return 0  # another process reminded this family first
            title = await self._world_title(conn, c.family_id)
        text = quest_waiting_text(c.locale, title, c.quest_title)
        delivery = _Delivery(
            channel, targets, Reminder(c.family_id, "quest_waiting", c.locale, text)
        )
        (outcome,) = await self._deliver([delivery])
        async with self._engine.begin() as conn:
            await self._settle(conn, outcome)
        return 1

    @staticmethod
    def _zone(name: str) -> ZoneInfo | None:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return None

    @staticmethod
    async def _world_title(conn: AsyncConnection, family_id: UUID) -> str | None:
        stored = await WorldRepository(conn).get(family_id)
        return stored.world.title if stored and stored.world else None

    @staticmethod
    async def _deliver(deliveries: list[_Delivery]) -> list[_Outcome]:
        outcomes = []
        for d in deliveries:
            delivered, gone = await d.channel.deliver(d.targets, d.reminder)
            outcomes.append(_Outcome(d, delivered, gone))
        return outcomes

    async def _settle(self, conn: AsyncConnection, outcome: _Outcome) -> None:
        d, delivered = outcome.delivery, outcome.delivered
        if outcome.gone:
            await d.channel.forget(conn, outcome.gone)
        if not delivered and d.reminder.kind == "quest_waiting":
            await PushRepository(conn).release_unanswered(
                d.reminder.family_id, d.channel.name
            )  # the day stays spent
        if delivered:
            funnel = FunnelService(FunnelRepository(conn), PilotService(PilotRepository(conn)))
            props = {"kind": d.reminder.kind, "channel": d.channel.name}
            await funnel.record_event(EventKind.REMINDER_SENT, d.reminder.family_id, None, props)

    async def run_forever(self) -> None:
        next_scan = 0.0
        while True:
            try:
                if await self.run_notify_once():
                    continue
                if time.monotonic() >= next_scan:
                    next_scan = time.monotonic() + self._settings.reminder_poll_s
                    await self.run_reminders_once()
            except Exception:  # the loop must outlive any one failed iteration
                logger.exception("reminder worker iteration failed")
            await asyncio.sleep(self._settings.world_poll_s)
