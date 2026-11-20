"""Polls the queue for cover jobs: reserve money, buy one picture, store it as WebP."""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.cover_text_check import CHECK_RESERVE_MICRO, CheckError, TextChecker
from app.agent.image_client import ImageResult, OpenRouterImageClient
from app.agent.money_gate import MoneyGate
from app.agent.webp import encode_webp
from app.core.config import Settings
from app.repositories.image_repository import ImageRepository
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_scene_repository import WorldSceneRepository
from app.services.cover_prompt import retry_prompt

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 2  # paid attempts per cover; a failed attempt keeps its reservation
REGEN_ATTEMPT_BASE = 100  # the regeneration of attempt n is reserved as attempt 100 + n


def _milestone_no(job: Job) -> int:
    """0 is the cover ordered with the world; a growth cover job carries its milestone's number."""
    return int(job.payload.get("milestone_no", 0))


class ImageWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        client: OpenRouterImageClient,
        settings: Settings,
        gate: MoneyGate | None = None,
        checker: TextChecker | None = None,
    ) -> None:
        self._engine, self._client, self._checker = engine, client, checker
        self._gate = gate or MoneyGate(engine, settings)
        self._retry_in = timedelta(seconds=settings.world_retry_delay_s)
        self._poll_s = settings.world_poll_s
        self._scene_on = settings.world3d_enabled
        # A reported price above the whole day's image cap is not a price: it is settled at the cap
        # (the gate then refuses image spend until the UTC day ends, even after a restart).
        # Clamped to bigint so an absurd cap setting cannot overflow the column.
        self._implausible_micro = min(
            round(settings.image_global_daily_cap_usd * 1_000_000), 2**63 - 1
        )
        # The smaller day cap: a picture dearer than it can never be paid, tomorrow or ever.
        self._fits_cap_micro = min(
            round(settings.image_family_daily_cap_usd * 1_000_000), self._implausible_micro
        )
        self.halted = False

    async def run_once(self) -> bool:
        """Process one due job; False when the queue is empty. The provider runs outside any tx."""
        async with self._engine.begin() as conn:
            job = await JobRepository(conn).claim(["image"])
            if job is None:
                return False
            world_job = UUID(job.payload["world_job_id"])
            prompt = await ImageRepository(conn).pending_prompt(
                job.family_id, world_job, _milestone_no(job)
            )
            if prompt is None:  # world regenerated, or the cover is already settled
                await JobRepository(conn).complete(job)
                logger.info("cover job %s makes no call: stale", job.id)
                return True
        micro = await self._reserve(job, world_job, prompt)
        if micro is None:
            return True
        try:
            result = await self._client.generate(prompt)
            first = await asyncio.to_thread(encode_webp, result.data)
        except Exception as exc:  # noqa: BLE001 (provider boundary: every failure counts as an attempt)
            # Class name only: provider text may carry request details. The reserve stays counted.
            logger.warning("cover job failed: %s attempt=%s", type(exc).__name__, job.attempts)
            await self._fail(job, world_job, type(exc).__name__, job.attempts >= MAX_ATTEMPTS)
            return True
        data, result = await self._screen_text(job, prompt, first, result)
        await self._store(job, world_job, data, result, micro)
        return True

    async def _reserve(self, job: Job, world_job: UUID, prompt: str) -> int | None:
        """Reserve the price; None when no paid call may be made (the job is already settled)."""
        if job.attempts > MAX_ATTEMPTS:  # claimed again and again: the worker keeps dying
            await self._fail(job, world_job, "AttemptsExceeded", final=True)
            return None
        micro = self._client.worst_case(prompt) + (CHECK_RESERVE_MICRO if self._checker else 0)
        reserved = await self._gate.reserve_image(job.family_id, job.id, job.attempts, micro)
        if reserved == "over_cap" and micro <= self._fits_cap_micro:
            await self._defer_to_next_day(job)  # the day's money is spent: wait for the next day
        elif reserved != "reserved":
            await self._fail(job, world_job, f"NoCall:{reserved}", final=True)
        return micro if reserved == "reserved" else None

    async def _screen_text(
        self, job: Job, prompt: str, data: bytes, result: ImageResult
    ) -> tuple[bytes, ImageResult]:
        """Look at the picture once; on writing, buy one stricter picture and keep that.

        Returns the bytes to store and the result whose cost settles this attempt (the check is
        added to it). Every failure here keeps the first picture: the check is never a reason to
        lose a cover.
        """
        if self._checker is None:
            return data, result
        try:
            verdict = await self._checker.has_text(data)
        except CheckError as exc:
            logger.warning("cover text check failed: %s job=%s", exc, job.id)
            return data, self._with_check(result, exc.cost_micro or 0)
        # noqa BLE001: the first image is already paid; a checker crash must not lose it or let
        # a lease reclaim buy another
        except Exception as exc:  # noqa: BLE001 (checker boundary: any failure keeps the picture)
            logger.warning("cover text check crashed: %s job=%s", type(exc).__name__, job.id)
            return data, result
        check = CHECK_RESERVE_MICRO if verdict.cost_micro is None else verdict.cost_micro
        paid = self._with_check(result, check)
        logger.info("cover text check: has_text=%s job=%s", verdict.has_text, job.id)
        if not verdict.has_text:
            return data, paid
        return (await self._regenerate(job, retry_prompt(prompt)) or data), paid

    @staticmethod
    def _with_check(result: ImageResult, check_micro: int) -> ImageResult:
        """The result with the check's price added; an unknown picture price stays unknown."""
        spent = None if result.cost_micro is None else result.cost_micro + check_micro
        return ImageResult(result.data, spent)

    async def _regenerate(self, job: Job, prompt: str) -> bytes | None:
        """The one stricter picture, reserved and settled on its own; None keeps the first."""
        micro = self._client.worst_case(prompt)
        key = REGEN_ATTEMPT_BASE + job.attempts
        reserved = await self._gate.reserve_image(job.family_id, job.id, key, micro)
        if reserved != "reserved":
            logger.info("cover job %s: no regeneration: %s", job.id, reserved)
            return None
        try:
            result = await self._client.generate(prompt)
            data = await asyncio.to_thread(encode_webp, result.data)
        except Exception as exc:  # noqa: BLE001 (provider boundary: the first picture stays)
            logger.warning("cover regeneration failed: %s job=%s", type(exc).__name__, job.id)
            return None
        cost = self._settled_cost(result.cost_micro, micro, job)
        async with self._engine.begin() as conn:
            await self._gate.settle(conn, job.id, key, cost)
        return data

    async def _defer_to_next_day(self, job: Job) -> None:
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).defer_unpaid(job):
                logger.warning("cover job %s lost its lease before deferring", job.id)
                return
        logger.info("cover job %s family %s: over the daily cap, deferred", job.id, job.family_id)

    async def _fail(self, job: Job, world_job: UUID, error: str, final: bool) -> None:
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).fail(job, error, final, self._retry_in):
                logger.warning("cover job %s lost its lease before failing", job.id)
                return
            if final:
                await ImageRepository(conn).mark_failed(
                    job.family_id, world_job, _milestone_no(job)
                )

    async def _store(
        self, job: Job, world_job: UUID, data: bytes, result: ImageResult, reserved: int
    ) -> None:
        """One transaction: cost settled, picture stored, job done."""
        actual = self._settled_cost(result.cost_micro, reserved, job)
        async with self._engine.begin() as conn:
            await self._gate.settle(conn, job.id, job.attempts, actual)
            n = _milestone_no(job)
            if await ImageRepository(conn).mark_ready(job.family_id, world_job, data, n):
                if n == 0:  # a growth cover never orders another scene
                    await self._order_scene(conn, job, world_job)
            else:
                logger.info("cover job %s was superseded: picture dropped", job.id)
            if not await JobRepository(conn).complete(job):
                logger.warning("cover job %s lost its lease before completing", job.id)

    def _settled_cost(self, reported: int | None, reserved: int, job: Job) -> int:
        """What to settle: the reported price, the reserve when none was reported, or the day's cap
        when the price is above it. A price above the reserve (or the cap) stops the worker."""
        implausible = reported is not None and reported > self._implausible_micro
        if reported is None:
            logger.warning("cover job %s: provider reported no price, charged the reserve", job.id)
        if implausible:
            actual = self._implausible_micro
        else:
            actual = reserved if reported is None else reported
        if implausible or actual > reserved:
            self.halted = True
            logger.error(
                "image cost %s above the reserve %s micro-USD: image worker stopped",
                "implausible" if implausible else actual,
                reserved,
            )
        return actual

    async def _order_scene(self, conn, job: Job, world_job: UUID) -> None:
        """Order the 3D scene of a world whose cover is stored."""
        scenes = WorldSceneRepository(conn)
        if self._scene_on and await scenes.create_pending(job.family_id, world_job):
            payload = {"world_job_id": str(world_job)}
            await JobRepository(conn).enqueue("scene", job.family_id, payload)

    async def run_forever(self) -> None:
        while not self.halted:
            try:
                if await self.run_once():
                    continue
            except Exception:  # the loop must outlive any one failed iteration
                logger.exception("image worker iteration failed")
            await asyncio.sleep(self._poll_s)
