"""Typed dependencies injected into every tool call. Services are Protocol placeholders."""

from dataclasses import dataclass
from typing import Protocol

from pydantic_ai.models import ModelRequestContext
from pydantic_ai.usage import RequestUsage


@dataclass(frozen=True, slots=True)
class FamilyStateView:
    """What the model may see about a family: no ids, tokens or Telegram data."""

    family_title: str
    member_names: tuple[str, ...]


class FamilyStateReader(Protocol):
    """Read port implemented later by the family service."""

    async def get_state(self, family_id: str) -> FamilyStateView: ...


class WorldSummaryReader(Protocol):
    """Short text about the family's ready world, or None."""

    async def summary(self, family_id: str) -> str | None: ...


class TurnSpend(Protocol):
    """The money of one turn: each model request is reserved before it is sent, then settled."""

    def worst_case(self, request: ModelRequestContext) -> int:
        """Micro-USD this request can cost at most."""
        ...

    async def reserve(self, attempt: int, micro: int) -> bool:
        """True only when `micro` fits under both daily caps and the request may be sent."""
        ...

    async def settle(self, attempt: int, usage: RequestUsage) -> None:
        """Replace the reservation of request `attempt` with its actual cost."""
        ...


@dataclass(frozen=True, slots=True)
class GameDeps:
    """Per-turn dependencies: the family the event belongs to plus service handles."""

    family_id: str
    families: FamilyStateReader
    channel: str = "web"
    kind: str = "message"
    worlds: WorldSummaryReader | None = None
    spend: TurnSpend | None = None
