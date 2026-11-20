"""When the soft "quest waiting" reminder may go out. Channel-neutral: Telegram reuses it."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

QUEST_MIN_AGE = timedelta(hours=20)
MAX_UNANSWERED = 3


@dataclass(frozen=True, slots=True)
class QuestWaiting:
    family_id: UUID
    locale: str
    quest_title: str
    quest_at: datetime
    last_active_at: datetime | None
    last_sent_at: datetime | None
    unanswered: int

    @property
    def effective_unanswered(self) -> int:
        """Sends since the family was last in the game: any later visit starts the count over."""
        returned = (
            self.last_active_at is not None
            and self.last_sent_at is not None
            and self.last_active_at > self.last_sent_at
        )
        return 0 if returned else self.unanswered


def quest_waiting_due(c: QuestWaiting, now: datetime, tz: ZoneInfo, hours: range) -> bool:
    """Open quest waiting >= 20 h, local hour in `hours`, nobody in the game or reminded today,
    and fewer than 3 reminders in a row without a visit."""
    if now - c.quest_at < QUEST_MIN_AGE or c.effective_unanswered >= MAX_UNANSWERED:
        return False
    local = now.astimezone(tz)
    if local.hour not in hours:
        return False
    today = local.date()
    seen = (c.last_active_at, c.last_sent_at)
    return all(t is None or t.astimezone(tz).date() != today for t in seen)
