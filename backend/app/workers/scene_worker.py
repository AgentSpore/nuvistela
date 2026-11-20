"""Polls the queue for scene jobs: reserve money, generate one 3D scene, store it."""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.money_gate import MoneyGate
from app.agent.world3d_client import SceneAssets, SceneError, SceneGenerator
from app.core.config import Settings
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_scene_repository import WorldSceneRepository
from app.services.cover_prompt import SAFETY_ENDING, YOUNG_CHILD_ENDING

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 2  # paid attempts per scene; a failed attempt keeps its reservation
LEASE = timedelta(minutes=15)  # longer than one generation (10 min), so no one claims it twice
SCENE_ENDING = f"{SAFETY_ENDING} A bright daytime scene, nothing frightening."


def scene_prompt(cover_prompt: str) -> str:
    """The scrubbed cover prompt minus its ending (the young-child one tells the age), plus ours."""
    base = cover_prompt.removesuffix(YOUNG_CHILD_ENDING).removesuffix(SAFETY_ENDING)
    return f"{base.strip(' ,.;:')}. {SCENE_ENDING}"


class SceneWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        client: SceneGenerator,
        settings: Settings,
    ) -> None:
        self._engine = engine
        self._client = client
        self._poll_s = settings.world_poll_s
        self._retry_in = timedelta(seconds=settings.world_retry_delay_s)
        self._gate = MoneyGate(engine, settings)

    async def run_once(self) -> bool:
        """Process one due job; False when the queue is empty. The provider runs outside any tx."""
        async with self._engine.begin() as conn:
            job = await JobRepository(conn).claim(["scene"], LEASE)
            if job is None:
                return False
            world_job = UUID(job.payload["world_job_id"])
            prompt = await WorldSceneRepository(conn).pending_prompt(job.family_id, world_job)
            if prompt is None:  # world regenerated, or the scene is already settled
                await JobRepository(conn).complete(job)
                logger.info("scene job %s makes no call: stale", job.id)
                return True
        if not await self._may_call(job, world_job):
            return True
        try:
            assets = await self._client.generate(scene_prompt(prompt))
        except Exception as exc:  # noqa: BLE001 (provider boundary: every failure counts as an attempt)
            # SceneError messages are ours by contract; anything else may carry provider text
            # (request details), so only its class is kept. The reserve stays counted.
            error = f"SceneError: {exc}" if isinstance(exc, SceneError) else type(exc).__name__
            logger.warning("scene job failed: %s attempt=%s", error, job.attempts)
            await self._fail(job, world_job, error, job.attempts >= MAX_ATTEMPTS)
            return True
        await self._store(job, world_job, assets)
        return True

    async def _may_call(self, job: Job, world_job: UUID) -> bool:
        """Reserve the price; False when no paid call may be made (the job is already settled)."""
        if job.attempts > MAX_ATTEMPTS:  # claimed again and again: the worker keeps dying
            await self._fail(job, world_job, "AttemptsExceeded", final=True)
            return False
        micro = self._client.price_micro
        reserved = await self._gate.reserve_world3d(job.family_id, job.id, job.attempts, micro)
        if reserved == "over_cap":  # the day's money is spent: wait for the next UTC day
            await self._defer_to_next_day(job)
        elif reserved != "reserved":
            await self._fail(job, world_job, f"NoCall:{reserved}", final=True)
        return reserved == "reserved"

    async def _defer_to_next_day(self, job: Job) -> None:
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).defer_unpaid(job):
                logger.warning("scene job %s lost its lease before deferring", job.id)
                return
        logger.info("scene job %s family %s: over the daily cap, deferred", job.id, job.family_id)

    async def _fail(self, job: Job, world_job: UUID, error: str, final: bool) -> None:
        async with self._engine.begin() as conn:
            released = await JobRepository(conn).fail(job, error, final, self._retry_in)
            if not released:
                logger.warning("scene job %s lost its lease before failing", job.id)
            elif final:
                await WorldSceneRepository(conn).mark_failed(job.family_id, world_job)

    async def _store(self, job: Job, world_job: UUID, assets: SceneAssets) -> None:
        """One transaction: cost settled at the table price, scene stored, job done."""
        async with self._engine.begin() as conn:
            await self._gate.settle(conn, job.id, job.attempts, self._client.price_micro)
            stored = await WorldSceneRepository(conn).mark_ready(
                job.family_id, world_job, assets.spz, assets.panorama_webp
            )
            if not stored:
                logger.info("scene job %s was superseded: scene dropped", job.id)
            if not await JobRepository(conn).complete(job):
                logger.warning("scene job %s lost its lease before completing", job.id)

    async def run_forever(self) -> None:
        while True:
            try:
                if await self.run_once():
                    continue
            except Exception:  # the loop must outlive any one failed iteration
                logger.exception("scene worker iteration failed")
            await asyncio.sleep(self._poll_s)
