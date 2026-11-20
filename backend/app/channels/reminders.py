"""What a reminder channel (Web Push, Telegram) offers the reminder worker."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from app.channels.push.rules import QuestWaiting
from app.channels.push.schemas import ReminderKind


@dataclass(frozen=True)
class Reminder:
    family_id: UUID
    kind: ReminderKind
    locale: str
    text: str  # titles only: it shows on a lock screen


class ReminderChannel[T](Protocol):
    name: str  # the `reminder_state.channel` value

    async def targets(self, conn: AsyncConnection, family_id: UUID) -> Sequence[T]: ...

    async def candidates(
        self, conn: AsyncConnection, older_than: datetime
    ) -> list[QuestWaiting]: ...

    async def deliver(self, targets: Sequence[T], reminder: Reminder) -> tuple[int, list[Any]]:
        """Send to every target; returns how many accepted and which targets are gone."""
        ...

    async def forget(self, conn: AsyncConnection, gone: list[Any]) -> None: ...
