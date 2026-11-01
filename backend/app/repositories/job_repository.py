"""Shared job queue. Claiming uses FOR UPDATE SKIP LOCKED so workers never wait on each other."""

import json
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class Job:
    id: UUID
    kind: str
    family_id: UUID
    payload: dict
    attempts: int


class JobRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def enqueue(self, kind: str, family_id: UUID, payload: dict) -> UUID:
        row = await self._conn.execute(
            text(
                "INSERT INTO jobs (kind, family_id, payload)"
                " VALUES (:kind, :fid, CAST(:payload AS jsonb)) RETURNING id"
            ),
            {"kind": kind, "fid": family_id, "payload": json.dumps(payload)},
        )
        return row.scalar_one()

    async def count_recent(self, kind: str, family_id: UUID, window: timedelta) -> int:
        row = await self._conn.execute(
            text(
                "SELECT count(*) FROM jobs WHERE kind = :kind AND family_id = :fid"
                " AND created_at > now() - CAST(:window AS interval)"
            ),
            {"kind": kind, "fid": family_id, "window": window},
        )
        return row.scalar_one()

    async def claim(
        self,
        kinds: list[str],
        lease: timedelta = timedelta(minutes=5),
        family_id: UUID | None = None,
    ) -> Job | None:
        """Take the oldest due job (or a 'running' one whose lease expired) and count an attempt."""
        row = (
            await self._conn.execute(
                text(
                    "UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1"
                    " WHERE id = (SELECT id FROM jobs WHERE kind = ANY(:kinds)"
                    "   AND (CAST(:fid AS uuid) IS NULL OR family_id = CAST(:fid AS uuid))"
                    "   AND next_run_at <= now()"
                    "   AND (status = 'pending'"
                    "     OR (status = 'running' AND locked_at < now() - CAST(:lease AS interval)))"
                    "   ORDER BY next_run_at LIMIT 1 FOR UPDATE SKIP LOCKED)"
                    " RETURNING id, kind, family_id, payload, attempts"
                ),
                {"kinds": kinds, "fid": family_id, "lease": lease},
            )
        ).first()
        return (
            None if row is None else Job(row.id, row.kind, row.family_id, row.payload, row.attempts)
        )

    async def complete(self, job_id: UUID) -> None:
        await self._conn.execute(
            text("UPDATE jobs SET status = 'done', locked_at = NULL WHERE id = :id"), {"id": job_id}
        )

    async def fail(self, job: Job, error: str, max_attempts: int, retry_in: timedelta) -> bool:
        """Release the job for a retry, or mark it failed. True when attempts are exhausted."""
        exhausted = job.attempts >= max_attempts
        await self._conn.execute(
            text(
                "UPDATE jobs SET status = :status, locked_at = NULL, last_error = :error,"
                " next_run_at = now() + CAST(:retry AS interval) WHERE id = :id"
            ),
            {
                "id": job.id,
                "status": "failed" if exhausted else "pending",
                "error": error,
                "retry": retry_in,
            },
        )
        return exhausted
