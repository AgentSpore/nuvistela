from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    LANDING_VIEW = "landing_view"
    WAITLIST_JOIN = "waitlist_join"
    FAMILY_CREATED = "family_created"
    WORLD_READY = "world_ready"
    QUEST_CREATED = "quest_created"
    QUEST_CONFIRMED = "quest_confirmed"
    CHAPTER_READY = "chapter_ready"
    MEMBER_FIRST_SEEN = "member_first_seen"
    RETURN_D1 = "return_d1"
    RETURN_D7 = "return_d7"


# Whitelist behind F-1: anything else (email, names, message text) is refused at the write.
ALLOWED_PROPS = frozenset({"locale", "utm_source", "family_size", "kids_age_bands"})

RETURN_DAYS = {1: EventKind.RETURN_D1, 7: EventKind.RETURN_D7}

# (step, baseline step its conversion is measured against)
FUNNEL_STEPS: tuple[tuple[EventKind, EventKind | None], ...] = (
    (EventKind.LANDING_VIEW, None),
    (EventKind.WAITLIST_JOIN, EventKind.LANDING_VIEW),
    (EventKind.FAMILY_CREATED, EventKind.LANDING_VIEW),
    (EventKind.WORLD_READY, EventKind.FAMILY_CREATED),
    (EventKind.QUEST_CREATED, EventKind.WORLD_READY),
    (EventKind.QUEST_CONFIRMED, EventKind.QUEST_CREATED),
    (EventKind.CHAPTER_READY, EventKind.QUEST_CONFIRMED),
    (EventKind.RETURN_D1, EventKind.FAMILY_CREATED),
    (EventKind.RETURN_D7, EventKind.FAMILY_CREATED),
)


@dataclass(frozen=True)
class FunnelStep:
    kind: EventKind
    count: int
    conversion: float | None
