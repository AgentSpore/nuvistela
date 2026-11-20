"""Money counted against the daily caps. Amounts are integer micro-USD (1 USD = 1_000_000)."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# Start of the current UTC day: the Q13 day boundary of both caps.
_UTC_DAY = "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
# One lock id for every spend decision: the global cap needs all of them serialised anyway.
_LOCK_ID = 7_021_998_342


class SpendRepository:
    """Spend of one call kind (`text`, `image` or `world3d`): its totals and reservations."""

    def __init__(self, conn: AsyncConnection, kind: str = "text") -> None:
        self._conn = conn
        self._kind = kind

    async def lock(self) -> None:
        """Serialise spend decisions until the transaction ends."""
        await self._conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _LOCK_ID})

    async def day_totals(self, family_id: UUID) -> tuple[int, int]:
        """(family, global) micro-USD of today for this kind: actual once settled, else reserve."""
        spent = "coalesce(actual_micro_usd, reserved_micro_usd)"
        row = (
            await self._conn.execute(
                text(
                    f"SELECT coalesce(sum({spent}) FILTER (WHERE family_id = :fid), 0),"
                    f" coalesce(sum({spent}), 0) FROM llm_spend"
                    f" WHERE kind = :kind AND created_at >= {_UTC_DAY}"
                ),
                {"fid": family_id, "kind": self._kind},
            )
        ).one()
        return int(row[0]), int(row[1])

    async def reserve(
        self, family_id: UUID, chapter_id: UUID | None, job_id: UUID, attempt: int, micro: int
    ) -> bool:
        """Insert the reservation; False when this (job, attempt) already has one."""
        result = await self._conn.execute(
            text(
                "INSERT INTO llm_spend"
                " (family_id, chapter_id, job_id, attempt, reserved_micro_usd, kind)"
                " VALUES (:fid, :cid, :job, :attempt, :micro, :kind)"
                " ON CONFLICT (job_id, attempt) DO NOTHING"
            ),
            {
                "fid": family_id,
                "cid": chapter_id,
                "job": job_id,
                "attempt": attempt,
                "micro": micro,
                "kind": self._kind,
            },
        )
        return result.rowcount == 1

    async def settle(self, job_id: UUID, attempt: int, actual_micro: int) -> bool:
        """Replace the reserve with the actual cost; False when nothing was reserved."""
        result = await self._conn.execute(
            text(
                "UPDATE llm_spend SET actual_micro_usd = :actual, state = 'settled'"
                " WHERE job_id = :job AND attempt = :attempt"
            ),
            {"job": job_id, "attempt": attempt, "actual": actual_micro},
        )
        return result.rowcount == 1
