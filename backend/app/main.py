import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from aiogram import Bot
from aiogram.exceptions import AiogramError
from aiogram.utils.token import TokenValidationError
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
from app.api.v1.telegram import router as telegram_router
from app.api.v1.world import router as world_router
from app.channels.telegram.handler import TelegramHandler
from app.channels.telegram.runner import UpdateRunner
from app.channels.telegram.secret import is_valid_webhook_secret
from app.channels.telegram.sender import AiogramSender, TelegramSender
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


class TelegramRuntime:
    """What the webhook route needs: the update runner and the sender's cleanup."""

    def __init__(self, runner: UpdateRunner, sender: TelegramSender) -> None:
        self.runner = runner
        self.sender = sender

    async def close(self) -> None:
        if isinstance(self.sender, AiogramSender):
            await self.sender.close()


async def _stop_telegram(telegram: TelegramRuntime | None) -> None:
    if telegram is not None:
        await telegram.runner.shutdown()
        await telegram.close()


def _build_telegram(
    app: FastAPI, settings: Settings, sender: TelegramSender | None
) -> TelegramRuntime | None:
    """None (route answers 404) unless the bot token and the webhook secret are both set."""
    if not (settings.telegram_bot_token and settings.telegram_webhook_secret):
        return None
    if not is_valid_webhook_secret(settings.telegram_webhook_secret.get_secret_value()):
        logger.warning("Telegram webhook secret has an invalid format: starting without it")
        return None
    try:
        sender = sender or AiogramSender(Bot(settings.telegram_bot_token.get_secret_value()))
    except (AiogramError, TokenValidationError) as exc:
        logger.warning("Telegram is misconfigured (%s): starting without it", type(exc).__name__)
        return None
    return TelegramRuntime(
        UpdateRunner(
            TelegramHandler(app.state, sender).process,
            max_concurrent=settings.telegram_max_concurrent_updates,
        ),
        sender,
    )


def create_app(
    settings: Settings | None = None,
    *,
    agent: Agent[GameDeps, str] | None = None,
    telegram_sender: TelegramSender | None = None,
) -> FastAPI:
    """Build the app. `agent` replaces the OpenRouter game master (tests override its model).

    Telegram runs only with both a bot token and a webhook secret; `telegram_sender` replaces the
    real Bot API client (tests).
    """
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
            app.state.telegram = _build_telegram(app, settings, telegram_sender)
            yield
        finally:
            await _stop_telegram(app.state.telegram)
            if pool is not None:
                await pool.close()
            await health_engine.dispose()
            await engine.dispose()

    app = FastAPI(title="Bumbli", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(families_router)
    app.include_router(agent_router)
    app.include_router(telegram_router)
    app.include_router(world_router)
    register_error_handlers(app)
    return app
