import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai_harness.spend import PostgresSpendStore
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.deps import GameDeps
from app.agent.errors import AgentConfigError
from app.agent.factory import build_game_master
from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.v1.agent import router as agent_router
from app.api.v1.families import router as families_router
from app.core.config import Settings

logger = logging.getLogger(__name__)


def _build_or_degrade(
    settings: Settings, spend_store: PostgresSpendStore | None
) -> Agent[GameDeps, str] | None:
    """Build the game master; without LLM settings start degraded (agent None, 503 on turns)."""
    try:
        return build_game_master(settings, spend_store=spend_store)
    except AgentConfigError:
        logger.warning("LLM is not configured: starting without the game master")
        return None


def create_app(
    settings: Settings | None = None, *, agent: Agent[GameDeps, str] | None = None
) -> FastAPI:
    """Build the app. `agent` replaces the OpenRouter game master (tests override its model)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        connect_args = {"timeout": 3}
        engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
        # Own pool for /health: turns holding every pooled connection must not fail liveness.
        health_engine = create_async_engine(
            settings.database_url,
            connect_args=connect_args,
            pool_size=1,
            max_overflow=0,
        )
        app.state.engine = engine
        app.state.health_engine = health_engine
        pool = None
        app.state.spend_store = None
        if agent is None:
            # min_size=0: no connection until the first spend call, so startup does not
            # depend on the database being reachable.
            pool = await asyncpg.create_pool(
                settings.database_url.replace("+asyncpg", ""), min_size=0, max_size=4
            )
            app.state.spend_store = PostgresSpendStore(pool)
        try:
            app.state.agent = agent or _build_or_degrade(settings, app.state.spend_store)
            yield
        finally:
            if pool is not None:
                await pool.close()
            await health_engine.dispose()
            await engine.dispose()

    app = FastAPI(title="Bumbli", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(families_router)
    app.include_router(agent_router)
    register_error_handlers(app)
    return app
