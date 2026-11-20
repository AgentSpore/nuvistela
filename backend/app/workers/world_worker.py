"""Polls the job queue for world jobs; three failed attempts store the genre's fallback (W-1)."""

import asyncio
import logging
from datetime import timedelta

from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.money_gate import MoneyGate
from app.agent.world_generator import WorldGenerator
from app.core.config import Settings
from app.domain.family import AgeBand, Member
from app.domain.world import World
from app.repositories.adventure_repository import AdventureRepository
from app.repositories.family_repository import FamilyRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_repository import WorldRepository
from app.services.adventure_fallback import fallback_world_and_quest, first_quest_draft
from app.services.cover_prompt import cover_prompt

logger = logging.getLogger(__name__)


class WorldWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        generator: WorldGenerator,
        settings: Settings,
        gate: MoneyGate | None = None,
    ) -> None:
        self._engine, self._generator = engine, generator
        self._gate = gate or MoneyGate(engine, settings)
        self._max_attempts = settings.world_max_attempts
        self._retry_in = timedelta(seconds=settings.world_retry_delay_s)
        self._poll_s = settings.world_poll_s
        self._refusal_logged = False
        self._cover_on = bool(settings.image_model)

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
        spec = self._spec(job, members)
        micro = self._generator.worst_case(spec)
        reserved = await self._gate.reserve(job.family_id, job.id, job.attempts, micro)
        if reserved != "reserved":  # no paid call: the fallback world, as after the last attempt
            await self._record_failure(job, f"NoCall:{reserved}", members, final=True)
            return True
        try:
            world, usage = await self._generator.generate_with_usage(spec)
        except Exception as exc:  # noqa: BLE001 (generator boundary: every failure must count as an attempt)
            # Class name only: provider text may carry request details.
            logger.warning("world job failed: %s attempt=%s", type(exc).__name__, job.attempts)
            self._warn_once_on_refusal(exc, job)
            await self._record_failure(job, type(exc).__name__, members)
            return True
        async with self._engine.begin() as conn:
            await self._gate.settle(conn, job.id, job.attempts, self._generator.price.cost(usage))
            stored = await WorldRepository(conn).save(job.family_id, "ready", world, job.id)
            if stored:  # same transaction: a world is never ready while quest 1 is missing
                draft = first_quest_draft(world, job.payload["locale"])
                await AdventureRepository(conn).open_first_quest(job.family_id, None, draft)
                await self._order_cover(conn, job, world, members)
            if not await JobRepository(conn).complete(job):
                logger.warning("world job %s lost its lease before completing", job.id)
        if not stored:
            logger.info("world job %s was superseded: result dropped", job.id)
        return True

    async def _order_cover(self, conn, job: Job, world: World, members: list[Member]) -> None:
        """Order the one cover picture of a ready world, in the transaction that stored it."""
        if not (self._cover_on and world.cover_image_prompt):
            return
        young = any(m.age_band is AgeBand.B3_5 for m in members)
        prompt = cover_prompt(world.cover_image_prompt, young_child=young)
        if await ImageRepository(conn).create_pending(job.family_id, job.id, prompt):
            await JobRepository(conn).enqueue("image", job.family_id, {"world_job_id": str(job.id)})

    def _warn_once_on_refusal(self, exc: Exception, job: Job) -> None:
        """Tell the operator once that the provider refuses the world model.

        A refused request (e.g. WORLD_MODEL pricier than the configured max_price) otherwise
        shows up only as families quietly getting the fallback world. Class and status only.
        """
        if (
            isinstance(exc, ModelHTTPError)
            and job.attempts >= self._max_attempts
            and not self._refusal_logged
        ):
            self._refusal_logged = True
            logger.warning(
                "provider refused the world model, fallback world stored: %s status=%s;"
                " check WORLD_MODEL price against the configured world prices or reasoning support",
                type(exc).__name__,
                exc.status_code,
            )

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

    async def _record_failure(
        self, job: Job, error: str, members: list[Member], final: bool = False
    ) -> None:
        final = final or job.attempts >= self._max_attempts
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).fail(job, error, final, self._retry_in):
                logger.warning("world job %s lost its lease before failing", job.id)
                return
            if final:
                ids = [m.id for m in members]
                world, draft = fallback_world_and_quest(
                    job.payload["genre"], job.payload["locale"], ids
                )
                if await WorldRepository(conn).save(job.family_id, "fallback", world, job.id):
                    await AdventureRepository(conn).open_first_quest(job.family_id, None, draft)

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
