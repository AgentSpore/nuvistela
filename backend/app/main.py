from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai_harness.spend import PostgresSpendStore
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.deps import GameDeps
from app.agent.factory import build_game_master
from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.v1.agent import router as agent_router
from app.api.v1.families import router as families_router
from app.core.config import Settings


def create_app(
    settings: Settings | None = None, *, agent: Agent[GameDeps, str] | None = None
) -> FastAPI:
    """Build the app. `agent` replaces the OpenRouter game master (tests override its model)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, connect_args={"timeout": 3}
        )
        app.state.engine = engine
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
            # Fails startup with AgentConfigError when the LLM settings are missing.
            app.state.agent = agent or build_game_master(
                settings, spend_store=app.state.spend_store
            )
            yield
        finally:
            if pool is not None:
                await pool.close()
            await engine.dispose()

    app = FastAPI(title="Bumbli", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(families_router)
    app.include_router(agent_router)
    register_error_handlers(app)
    return app
