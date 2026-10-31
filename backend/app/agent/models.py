"""Event in, reply out: the whole public surface between channels and the game master."""

from dataclasses import dataclass
from typing import Literal

Channel = Literal["web", "telegram"]
EventKind = Literal["message", "quest_event", "schedule"]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Something that wakes the game master. `family_id` scopes tools; it is never sent as text.

    K2 decisions, deliberately open: `kind`/`channel` travel as a text prefix in the user message,
    so family text can imitate it; and `family_id` must not be `*` or contain `|` (the harness
    spend scope rejects those), so use UUIDs.
    """

    family_id: str
    channel: Channel
    kind: EventKind
    text: str


@dataclass(frozen=True, slots=True)
class AgentReply:
    """What the game master says back to the channel."""

    text: str
