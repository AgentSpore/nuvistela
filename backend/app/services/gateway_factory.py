"""Composition root of the game master for one transaction; web and channel adapters share it."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.datastructures import State

from app.agent.chat_spend import ChatSpend, chat_price
from app.agent.deps import GameDeps
from app.agent.errors import AgentUnavailableError
from app.agent.money_gate import MoneyGate
from app.agent.postgres_store import PostgresConversationStore
from app.agent.runtime import GameMasterRuntime
from app.repositories.family_repository import FamilyRepository
from app.repositories.world_repository import WorldRepository
from app.services.agent_gateway import AgentGateway
from app.services.family_state import SqlFamilyState
from app.services.world_summary import SqlWorldSummary

DB_CONNECT_TIMEOUT_S = 3  # connect timeout of every engine of the app


def money_engine(state: State) -> AsyncEngine:
    """Engine of the money gate, one per app, with no pool of its own to size or dispose.

    A turn holds a pooled connection while its model request is reserved and settled in other
    transactions; drawing those from the same pool deadlocks once enough turns run at once.
    """
    engine = getattr(state, "money_engine", None)
    if engine is None:
        engine = state.money_engine = create_async_engine(
            state.engine.url,
            poolclass=NullPool,
            connect_args={"timeout": DB_CONNECT_TIMEOUT_S},
        )
    return engine


def build_agent_gateway(state: State, conn: AsyncConnection) -> AgentGateway:
    """The store appends in `conn`'s transaction, so the gateway is built per transaction."""
    if state.agent is None:
        raise AgentUnavailableError("LLM is not configured")
    repo = FamilyRepository(conn)
    families, worlds = SqlFamilyState(repo), SqlWorldSummary(repo, WorldRepository(conn))
    settings, engine = state.settings, money_engine(state)
    gate = MoneyGate(engine, settings)

    def deps(family_id: str) -> GameDeps:
        # One ChatSpend per turn: its id keys that turn's reservations in llm_spend.
        spend = ChatSpend(
            gate, engine, chat_price(settings), settings.chat_max_tokens, UUID(family_id)
        )
        return GameDeps(family_id=family_id, families=families, worlds=worlds, spend=spend)

    runtime = GameMasterRuntime(
        state.agent,
        deps,
        state.settings,
        PostgresConversationStore(conn),
    )
    return AgentGateway(runtime)
