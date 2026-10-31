"""Tool registration: write an `async def` taking RunContext[GameDeps], register it here."""

from pydantic_ai import Agent, RunContext

from app.agent.deps import FamilyStateView, GameDeps


async def get_family_state(ctx: RunContext[GameDeps]) -> FamilyStateView:
    """Read-only: the title and member names of the family this event belongs to."""
    return await ctx.deps.families.get_state(ctx.deps.family_id)


def register_tools(agent: Agent[GameDeps, str]) -> None:
    """Attach every game master tool; the family comes from deps, never from model arguments."""
    agent.tool(get_family_state)
