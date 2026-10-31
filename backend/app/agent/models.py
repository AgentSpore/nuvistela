"""Event in, reply out: the whole public surface between channels and the game master."""

from dataclasses import dataclass
from typing import Literal

Channel = Literal["web", "telegram"]
EventKind = Literal["message", "quest_event", "schedule"]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Something that wakes the game master. `family_id` scopes tools; it is never sent as text.

    `kind` and `channel` reach the model out of band (dynamic instructions built from deps), never
    as a prefix of `text`, so family text cannot imitate them. `family_id` must not be `*` or
    contain `|` (the harness spend scope rejects those), so use UUIDs. `member_id` is who sent it;
    None for events the system raises itself and for channel users not mapped to a member yet.
    """

    family_id: str
    channel: Channel
    kind: EventKind
    text: str
    member_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentReply:
    """What the game master says back to the channel."""

    text: str
