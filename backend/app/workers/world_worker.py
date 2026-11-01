"""Polls the job queue for world jobs; three failed attempts store the genre's fallback (W-1)."""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.world_generator import WorldGenerator, WorldInvalid
from app.core.config import Settings
from app.domain.world_fallback import fallback_world
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_repository import WorldRepository

logger = logging.getLogger(__name__)
_FAILURES = (ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded, TimeoutError, WorldInvalid)


class WorldWorker:
    def __init__(self, engine: AsyncEngine, generator: WorldGenerator, settings: Settings) -> None:
        self._engine, self._generator = engine, generator
        self._max_attempts = settings.world_max_attempts
        self._retry_in = timedelta(seconds=settings.world_retry_delay_s)
        self._poll_s = settings.world_poll_s

    async def run_once(self) -> bool:
        """Process one due job; False when the queue is empty. The model runs outside any tx."""
        async with self._engine.begin() as conn:
            job = await JobRepository(conn).claim(["world"])
        if job is None:
            return False
        try:
            world = await self._generator.generate(job.payload)
        except _FAILURES as exc:
            # Class name only: provider text may carry request details.
            logger.warning("world job failed: %s attempt=%s", type(exc).__name__, job.attempts)
            await self._record_failure(job, type(exc).__name__)
            return True
        async with self._engine.begin() as conn:
            await WorldRepository(conn).save(job.family_id, "ready", world)
            await JobRepository(conn).complete(job.id)
        return True

    async def _record_failure(self, job: Job, error: str) -> None:
        async with self._engine.begin() as conn:
            exhausted = await JobRepository(conn).fail(
                job, error, self._max_attempts, self._retry_in
            )
            if exhausted:
                ids = [UUID(m["member_id"]) for m in job.payload["members"]]
                world = fallback_world(job.payload["genre"], job.payload["locale"], ids)
                await WorldRepository(conn).save(job.family_id, "fallback", world)

    async def run_forever(self) -> None:
        while True:
            try:
                if await self.run_once():
                    continue
            except (
                Exception
            ):  # the loop must outlive any one failed iteration; logged with traceback
                logger.exception("world worker iteration failed")
            await asyncio.sleep(self._poll_s)
