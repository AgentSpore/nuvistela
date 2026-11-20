import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from aiogram import Bot
from aiogram.exceptions import AiogramError
from aiogram.utils.token import TokenValidationError
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai_harness.spend import PostgresSpendStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.chapter_writer import build_chapter_writer
from app.agent.cover_text_check import OpenRouterTextChecker
from app.agent.deps import GameDeps
from app.agent.errors import AgentConfigError
from app.agent.factory import build_game_master
from app.agent.image_client import OpenRouterImageClient
from app.agent.world3d_client import WorldLabsClient
from app.agent.world_generator import WorldGenerator, build_world_generator
from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.v1.adventure import router as adventure_router
from app.api.v1.agent import router as agent_router
from app.api.v1.families import router as families_router
from app.api.v1.funnel import router as funnel_router
from app.api.v1.media import router as media_router
from app.api.v1.push import router as push_router
from app.api.v1.share import router as share_router
from app.api.v1.telegram import router as telegram_router
from app.api.v1.world import router as world_router
from app.channels.push.channel import PushChannel
from app.channels.push.sender import PushSender, WebPushSender
from app.channels.reminders import ReminderChannel
from app.channels.telegram.handler import TelegramHandler
from app.channels.telegram.reminders import TelegramChannel
from app.channels.telegram.runner import UpdateRunner
from app.channels.telegram.secret import is_valid_webhook_secret
from app.channels.telegram.sender import AiogramSender, TelegramSender
from app.core.config import Settings
from app.services.admission import (
    FAMILY_CREATE_WINDOWS,
    INVITE_ACCEPT_WINDOWS,
    DailyCounter,
    WindowLimiter,
)
from app.services.gateway_factory import DB_CONNECT_TIMEOUT_S
from app.workers.chapter_worker import ChapterWorker
from app.workers.image_worker import ImageWorker
from app.workers.reminder_worker import ReminderWorker
from app.workers.scene_worker import SceneWorker
from app.workers.world_worker import WorldWorker

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


def _build_world_generator(settings: Settings) -> WorldGenerator | None:
    """None without LLM settings: world jobs then wait in the queue."""
    try:
        return build_world_generator(settings)
    except AgentConfigError:
        logger.warning("OPENROUTER_API_KEY is not set: world jobs are not processed")
        return None


def _create_engines(settings: Settings) -> tuple[AsyncEngine, AsyncEngine]:
    """The request engine and a one-connection engine reserved for /health."""
    connect_args = {"timeout": DB_CONNECT_TIMEOUT_S}
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    # Own pool for /health: turns holding every pooled connection must not fail liveness.
    health_engine = create_async_engine(
        settings.database_url, connect_args=connect_args, pool_size=1, max_overflow=0
    )
    return engine, health_engine


def _start_world_worker(
    engine: AsyncEngine, settings: Settings, generator: WorldGenerator | None
) -> asyncio.Task[None] | None:
    """Run the world queue worker unless disabled or OPENROUTER_API_KEY is not set."""
    generator = generator or _build_world_generator(settings)
    if generator is None or not settings.world_worker_enabled:
        return None
    return asyncio.create_task(WorldWorker(engine, generator, settings).run_forever())


def _start_chapter_worker(
    engine: AsyncEngine, settings: Settings, reminders: asyncio.Task[None] | None
) -> asyncio.Task[None] | None:
    """Run the chapter queue worker (same enable flag as the world worker) if the key is set."""
    if not settings.world_worker_enabled:
        return None
    try:
        writer = build_chapter_writer(settings)
    except AgentConfigError:
        logger.warning("OPENROUTER_API_KEY is not set: chapter jobs are not processed")
        return None
    return asyncio.create_task(
        ChapterWorker(engine, writer, settings, notify=reminders is not None).run_forever()
    )


def _start_image_worker(engine: AsyncEngine, settings: Settings) -> asyncio.Task[None] | None:
    """Run the cover worker only with IMAGE_MODEL and the key set: otherwise no paid call exists."""
    if not (settings.image_model and settings.world_worker_enabled):
        return None
    try:
        client = OpenRouterImageClient(settings)
    except AgentConfigError:
        logger.warning("OPENROUTER_API_KEY is not set: cover jobs are not processed")
        return None
    return asyncio.create_task(
        ImageWorker(engine, client, settings, checker=OpenRouterTextChecker(settings)).run_forever()
    )


def _start_scene_worker(engine: AsyncEngine, settings: Settings) -> asyncio.Task[None] | None:
    """Run the scene worker only with WORLD3D_MODEL and WORLDLABS_API_KEY set: no paid call else."""
    if not settings.world_worker_enabled:
        return None
    if not settings.world3d_enabled:
        if settings.world3d_model:
            logger.warning("WORLD3D_MODEL is ignored: no key, no known price or above the cap")
        return None
    try:
        client = WorldLabsClient(settings)
    except AgentConfigError as exc:
        logger.warning("scene jobs are not processed: %s", exc)
        return None
    return asyncio.create_task(SceneWorker(engine, client, settings).run_forever())


async def _stop_worker(task: asyncio.Task[None] | None) -> None:
    """Cancel and wait, so the worker is not mid-query when the engine is disposed."""
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _stop_workers(*tasks: asyncio.Task[None] | None) -> None:
    """Stop the workers one by one, in the order given."""
    for task in tasks:
        await _stop_worker(task)


class TelegramRuntime:
    """What the webhook route needs: the update runner and the sender's cleanup."""

    def __init__(self, runner: UpdateRunner, sender: TelegramSender) -> None:
        self.runner = runner
        self.sender = sender

    async def close(self) -> None:
        if isinstance(self.sender, AiogramSender):
            await self.sender.close()


def _start_reminder_worker(app: FastAPI, sender: PushSender | None) -> asyncio.Task[None] | None:
    """Reminders go over Web Push (VAPID pair and subject set) and over Telegram (runtime up)."""
    settings, telegram = app.state.settings, app.state.telegram
    channels: list[ReminderChannel[Any]] = []
    if settings.push_enabled and settings.vapid_private_key and settings.vapid_subject:
        key = settings.vapid_private_key.get_secret_value()
        channels.append(PushChannel(sender or WebPushSender(key, settings.vapid_subject)))
    if telegram is not None:
        channels.append(TelegramChannel(telegram.sender, settings.site_url))
    if not channels:
        return None
    return asyncio.create_task(ReminderWorker(app.state.engine, channels, settings).run_forever())


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


def _include_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(families_router)
    app.include_router(agent_router)
    app.include_router(funnel_router)
    app.include_router(telegram_router)
    app.include_router(world_router)
    app.include_router(adventure_router)
    app.include_router(media_router)
    app.include_router(share_router)
    app.include_router(push_router)


def _init_admission(app: FastAPI) -> None:
    app.state.family_limiter = WindowLimiter(FAMILY_CREATE_WINDOWS)
    app.state.invite_limiter = WindowLimiter(INVITE_ACCEPT_WINDOWS)
    app.state.erased_today = DailyCounter()


def create_app(
    settings: Settings | None = None,
    *,
    agent: Agent[GameDeps, str] | None = None,
    telegram_sender: TelegramSender | None = None,
    world_generator: WorldGenerator | None = None,
    push_sender: PushSender | None = None,
) -> FastAPI:
    """Build the app. `agent` replaces the OpenRouter game master (tests override its model).

    Telegram runs only with both a bot token and a webhook secret; `telegram_sender` replaces the
    real Bot API client (tests). `push_sender` likewise replaces the Web Push client.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine, health_engine = _create_engines(settings)
        app.state.engine = engine
        app.state.health_engine = health_engine
        pool = None
        worker_task = chapter_task = image_task = reminder_task = scene_task = None
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
            worker_task = app.state.world_worker = _start_world_worker(
                engine, settings, world_generator
            )
            reminder_task = app.state.reminder_worker = _start_reminder_worker(app, push_sender)
            chapter_task = app.state.chapter_worker = _start_chapter_worker(
                engine, settings, reminder_task
            )
            image_task = app.state.image_worker = _start_image_worker(engine, settings)
            scene_task = _start_scene_worker(engine, settings)
            yield
        finally:
            await _stop_workers(reminder_task, scene_task, image_task, chapter_task, worker_task)
            await _stop_telegram(app.state.telegram)
            if pool is not None:
                await pool.close()
            await health_engine.dispose()
            await engine.dispose()
            if money := getattr(app.state, "money_engine", None):
                await money.dispose()

    app = FastAPI(title="Bumbli", lifespan=lifespan)
    app.state.settings = settings
    _init_admission(app)
    _include_routers(app)
    register_error_handlers(app)
    return app
