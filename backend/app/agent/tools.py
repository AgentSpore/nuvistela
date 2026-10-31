"""Game master tools. Add one: write an `async def` taking RunContext[GameDeps], list it here."""

from pydantic_ai import RunContext
from pydantic_ai.capabilities import Toolset
from pydantic_ai.toolsets import FunctionToolset

from app.agent.deps import FamilyStateView, GameDeps


async def get_family_state(ctx: RunContext[GameDeps]) -> FamilyStateView:
    """Read-only: the title and member names of the family this event belongs to."""
    return await ctx.deps.families.get_state(ctx.deps.family_id)


def game_tools() -> Toolset[GameDeps]:
    """Capability exposing every game master tool; the family comes from deps, not the model."""
    return Toolset(FunctionToolset([get_family_state]))
