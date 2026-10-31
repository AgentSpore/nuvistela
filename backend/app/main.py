from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.health import router as health_router
from app.api.v1.families import register_error_handlers
from app.api.v1.families import router as families_router
from app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, connect_args={"timeout": 3}
        )
        app.state.engine = engine
        yield
        await engine.dispose()

    app = FastAPI(title="Bumbli", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(families_router)
    register_error_handlers(app)
    return app
