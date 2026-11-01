"""Composition root of the game master for one transaction; web and channel adapters share it."""

from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.datastructures import State

from app.agent.deps import GameDeps
from app.agent.errors import AgentUnavailableError
from app.agent.postgres_store import PostgresConversationStore
from app.agent.runtime import GameMasterRuntime
from app.repositories.family_repository import FamilyRepository
from app.repositories.world_repository import WorldRepository
from app.services.agent_gateway import AgentGateway
from app.services.family_state import SqlFamilyState
from app.services.world_summary import SqlWorldSummary


def build_agent_gateway(state: State, conn: AsyncConnection) -> AgentGateway:
    """The store appends in `conn`'s transaction, so the gateway is built per transaction."""
    if state.agent is None:
        raise AgentUnavailableError("LLM is not configured")
    repo = FamilyRepository(conn)
    families, worlds = SqlFamilyState(repo), SqlWorldSummary(repo, WorldRepository(conn))
    runtime = GameMasterRuntime(
        state.agent,
        lambda family_id: GameDeps(family_id=family_id, families=families, worlds=worlds),
        state.settings,
        PostgresConversationStore(conn),
    )
    return AgentGateway(runtime)
