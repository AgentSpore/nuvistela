import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ImageStatus = Literal["pending", "ready", "failed"]


@dataclass(frozen=True)
class CoverState:
    """Where the current world's cover stands; sha is set only when ready."""

    status: ImageStatus
    sha: str | None
    deferred: bool = False  # pending, and its job waits for the next UTC day's budget


# The cover's job was handed back until the next UTC midnight (the day's image budget is spent);
# a retry after a failure is due within seconds, never exactly at midnight.
_DEFERRED = (
    "EXISTS (SELECT 1 FROM jobs j"
    " WHERE j.kind = 'image' AND j.family_id = i.family_id AND j.status = 'pending'"
    " AND j.payload->>'world_job_id' = i.world_job_id::text"
    " AND COALESCE((j.payload->>'milestone_no')::int, 0) = i.milestone_no"
    " AND j.next_run_at > now()"
    " AND j.next_run_at = date_trunc('day', j.next_run_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')"
)


def _key(milestone_no: int) -> dict:
    """The row of a cover: the first one (milestone 0) is 'cover', a growth cover 'cover_growth'."""
    return {"kind": "cover" if milestone_no == 0 else "cover_growth", "n": milestone_no}


class ImageRepository:
    """World pictures kept in Postgres: the cover and the growth covers of later milestones."""

    # Never selects `bytes`: this runs on every world read.
    # The newest ready cover wins; while none is ready, the newest ordered one is reported.
    _COVER_STATE = (
        f"SELECT i.status, i.sha256, (i.status = 'pending' AND {_DEFERRED}) AS deferred"
        " FROM world_images i"
        " JOIN worlds w ON w.family_id = i.family_id AND w.job_id = i.world_job_id"
        " WHERE i.family_id = :fid AND i.kind IN ('cover', 'cover_growth')"
        " ORDER BY (i.status = 'ready') DESC, i.milestone_no DESC LIMIT 1"
    )

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create_pending(
        self, family_id: UUID, world_job_id: UUID, prompt: str, milestone_no: int = 0
    ) -> bool:
        """Order a cover of a world version; False when it was already ordered."""
        result = await self._conn.execute(
            text(
                "INSERT INTO world_images (family_id, world_job_id, kind, milestone_no, prompt)"
                " VALUES (:fid, :job, :kind, :n, :prompt)"
                " ON CONFLICT (family_id, world_job_id, kind, milestone_no) DO NOTHING"
            ),
            {"fid": family_id, "job": world_job_id, "prompt": prompt, **_key(milestone_no)},
        )
        return result.rowcount == 1

    async def pending_prompt(
        self, family_id: UUID, world_job_id: UUID, milestone_no: int = 0
    ) -> str | None:
        """The prompt to buy, None unless that cover is pending and its world is still current."""
        row = await self._conn.execute(
            text(
                "SELECT i.prompt FROM world_images i"
                " JOIN worlds w ON w.family_id = i.family_id AND w.job_id = i.world_job_id"
                " WHERE i.family_id = :fid AND i.world_job_id = :job AND i.kind = :kind"
                " AND i.milestone_no = :n AND i.status = 'pending' AND w.status = 'ready'"
            ),
            {"fid": family_id, "job": world_job_id, **_key(milestone_no)},
        )
        return row.scalar_one_or_none()

    async def mark_ready(
        self, family_id: UUID, world_job_id: UUID, data: bytes, milestone_no: int = 0
    ) -> bool:
        """Store the bytes and their sha256; False when the row is missing or not pending."""
        result = await self._conn.execute(
            text(
                "UPDATE world_images SET status = 'ready', sha256 = :sha, bytes = :data,"
                " updated_at = now() WHERE family_id = :fid AND world_job_id = :job"
                " AND kind = :kind AND milestone_no = :n AND status = 'pending'"
            ),
            {
                "fid": family_id,
                "job": world_job_id,
                "sha": hashlib.sha256(data).hexdigest(),
                "data": data,
                **_key(milestone_no),
            },
        )
        return result.rowcount == 1

    async def mark_failed(self, family_id: UUID, world_job_id: UUID, milestone_no: int = 0) -> bool:
        """False when the row is missing or not pending."""
        result = await self._conn.execute(
            text(
                "UPDATE world_images SET status = 'failed', updated_at = now()"
                " WHERE family_id = :fid AND world_job_id = :job AND kind = :kind"
                " AND milestone_no = :n AND status = 'pending'"
            ),
            {"fid": family_id, "job": world_job_id, **_key(milestone_no)},
        )
        return result.rowcount == 1

    async def cover_state(self, family_id: UUID) -> CoverState | None:
        """The cover of the family's current world, None when none was ordered for it."""
        row = (await self._conn.execute(text(self._COVER_STATE), {"fid": family_id})).first()
        return None if row is None else CoverState(row.status, row.sha256, row.deferred)

    async def growth_pending(self, family_id: UUID) -> bool:
        """True while a growth cover of the current world is being made (not while deferred)."""
        row = await self._conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM world_images i JOIN worlds w"
                " ON w.family_id = i.family_id AND w.job_id = i.world_job_id"
                " WHERE i.family_id = :fid AND i.kind = 'cover_growth' AND i.status = 'pending'"
                f" AND NOT {_DEFERRED})"
            ),
            {"fid": family_id},
        )
        return bool(row.scalar_one())

    async def ready_bytes(self, family_id: UUID, sha: str) -> bytes | None:
        """The bytes of a ready picture of this family, None for anything else."""
        row = await self._conn.execute(
            text(
                "SELECT bytes FROM world_images"
                " WHERE family_id = :fid AND sha256 = :sha AND status = 'ready' LIMIT 1"
            ),
            {"fid": family_id, "sha": sha},
        )
        return row.scalar_one_or_none()
