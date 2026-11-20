"""The money cap, checked before every paid call.

Harness SpendLimits adds cost only after a response and reserves nothing, so parallel runs all
pass its check. The gate reserves the worst-case cost in `llm_spend` under an advisory lock
first, then replaces it with the real cost. The worst case is only real because every request
also carries `max_tokens` and the provider `max_price` of the same `ModelPrice`.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

from pydantic_ai.models.openrouter import OpenRouterProviderConfig
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import Settings
from app.repositories.spend_repository import SpendRepository

logger = logging.getLogger(__name__)
Reservation = Literal["reserved", "over_cap", "duplicate"]
SpendKind = Literal["text", "image", "world3d"]
_MICRO = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens of one model; the same number is micro-USD per token."""

    in_usd_per_mtok: float
    out_usd_per_mtok: float

    def worst_case(self, input_bytes: int, max_output_tokens: int) -> int:
        """Most one call can cost, in micro-USD (a token is at least one byte of input)."""
        return math.ceil(
            input_bytes * self.in_usd_per_mtok + max_output_tokens * self.out_usd_per_mtok
        )

    def cost(self, usage: RunUsage) -> int:
        """Actual cost of a finished run, in micro-USD."""
        paid = (
            usage.input_tokens * self.in_usd_per_mtok + usage.output_tokens * self.out_usd_per_mtok
        )
        return math.ceil(paid)

    def zdr_routing(self) -> OpenRouterProviderConfig:
        """Zero-retention routing that also refuses any provider dearer than this price."""
        # The SDK types max_price values as int, but the API takes fractional USD per Mtok.
        price = {"prompt": self.in_usd_per_mtok, "completion": self.out_usd_per_mtok}
        return OpenRouterProviderConfig(
            data_collection="deny",
            zdr=True,
            require_parameters=True,
            max_price=cast("Any", price),
        )


class MoneyGate:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self._engine = engine
        # (family, global) daily cap per kind, micro-USD.
        self._caps: dict[SpendKind, tuple[int, int]] = {
            "text": (
                round(settings.llm_family_daily_cap_usd * _MICRO),
                round(settings.llm_global_daily_cap_usd * _MICRO),
            ),
            "image": (
                round(settings.image_family_daily_cap_usd * _MICRO),
                round(settings.image_global_daily_cap_usd * _MICRO),
            ),
            "world3d": (
                round(settings.world3d_family_daily_cap_usd * _MICRO),
                round(settings.world3d_global_daily_cap_usd * _MICRO),
            ),
        }

    async def reserve(
        self,
        family_id: UUID,
        job_id: UUID,
        attempt: int,
        micro: int,
        chapter_id: UUID | None = None,
    ) -> Reservation:
        """Reserve text `micro` under both daily caps; only "reserved" permits the paid call.

        "duplicate" means this job attempt already reserved (a redelivery): no second call.
        """
        return await self._reserve("text", family_id, (job_id, attempt), micro, chapter_id)

    async def reserve_image(
        self, family_id: UUID, job_id: UUID, attempt: int, micro: int
    ) -> Reservation:
        """Like `reserve`, under the image caps: image spend never reduces the text allowance."""
        return await self._reserve("image", family_id, (job_id, attempt), micro)

    async def reserve_world3d(
        self, family_id: UUID, job_id: UUID, attempt: int, micro: int
    ) -> Reservation:
        """Like `reserve`, under the 3D world caps: neither text nor pictures use them up."""
        return await self._reserve("world3d", family_id, (job_id, attempt), micro)

    async def _reserve(
        self,
        kind: SpendKind,
        family_id: UUID,
        job_attempt: tuple[UUID, int],
        micro: int,
        chapter_id: UUID | None = None,
    ) -> Reservation:
        family_cap, global_cap = self._caps[kind]
        async with self._engine.begin() as conn:
            spend = SpendRepository(conn, kind)
            await spend.lock()
            family_total, global_total = await spend.day_totals(family_id)
            if family_total + micro > family_cap or global_total + micro > global_cap:
                return "over_cap"
            if await spend.reserve(family_id, chapter_id, *job_attempt, micro):
                return "reserved"
            return "duplicate"

    async def settle(self, conn: AsyncConnection, job_id: UUID, attempt: int, actual: int) -> bool:
        """Record the actual cost in the caller's transaction; False (logged) if none reserved."""
        settled = await SpendRepository(conn).settle(job_id, attempt, actual)
        if not settled:
            logger.warning("no reservation to settle: job=%s attempt=%s", job_id, attempt)
        return settled
