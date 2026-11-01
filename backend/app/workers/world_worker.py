"""Polls the job queue for world jobs; three failed attempts store the genre's fallback (W-1)."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.world_generator import WorldGenerator
from app.core.config import Settings
from app.domain.family import Member
from app.domain.world_fallback import fallback_world
from app.repositories.family_repository import FamilyRepository
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_repository import WorldRepository

logger = logging.getLogger(__name__)


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
            members = await FamilyRepository(conn).list_members(job.family_id) if job else []
            current = await WorldRepository(conn).current_job_id(job.family_id) if job else None
            if job is not None and current != job.id:
                await JobRepository(conn).complete(job)
                logger.info("world job %s was superseded before generating", job.id)
                return True
        if job is None:
            return False
        if job.attempts > self._max_attempts:  # claimed again and again: the worker keeps dying
            await self._record_failure(job, "AttemptsExceeded", members)
            return True
        try:
            world = await self._generator.generate(self._spec(job, members))
        except Exception as exc:  # noqa: BLE001 (generator boundary: every failure must count as an attempt)
            # Class name only: provider text may carry request details.
            logger.warning("world job failed: %s attempt=%s", type(exc).__name__, job.attempts)
            await self._record_failure(job, type(exc).__name__, members)
            return True
        async with self._engine.begin() as conn:
            stored = await WorldRepository(conn).save(job.family_id, "ready", world, job.id)
            if not await JobRepository(conn).complete(job):
                logger.warning("world job %s lost its lease before completing", job.id)
        if not stored:
            logger.info("world job %s was superseded: result dropped", job.id)
        return True

    @staticmethod
    def _spec(job: Job, members: list[Member]) -> dict:
        """The generator input: queue payload plus members read now, so names never sit in jobs."""
        return {
            **job.payload,
            "members": [
                {"member_id": str(m.id), "age_band": m.age_band.value, "interests": m.interests}
                for m in members
            ],
            "private": [m.display_name for m in members],
        }

    async def _record_failure(self, job: Job, error: str, members: list[Member]) -> None:
        final = job.attempts >= self._max_attempts
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).fail(job, error, final, self._retry_in):
                logger.warning("world job %s lost its lease before failing", job.id)
                return
            if final:
                ids = [m.id for m in members]
                world = fallback_world(job.payload["genre"], job.payload["locale"], ids)
                await WorldRepository(conn).save(job.family_id, "fallback", world, job.id)

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
