from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# The family's story counters, for the row aliased `s` that carries `family_id`. The one source
# of both the public card and the sender's preview, so the two cannot disagree.
_STORY_COUNTS = (
    " (SELECT count(*) FROM quests q"
    "   WHERE q.family_id = s.family_id AND q.status = 'done') AS quests_done,"
    " (SELECT count(*) FROM chapters c"
    "   WHERE c.family_id = s.family_id AND c.status = 'ready') AS chapters"
)


@dataclass(frozen=True)
class StoryCounts:
    quests_done: int  # the family's quests marked done
    chapters: int  # the family's written (ready) chapters


@dataclass(frozen=True)
class Share:
    id: UUID
    title: str | None
    genre: str
    counts: StoryCounts


@dataclass(frozen=True)
class ActiveShare:
    id: UUID
    world_job_id: UUID
    title: str | None
    genre: str


@dataclass(frozen=True)
class NewShare:
    id: UUID
    family_id: UUID
    world_job_id: UUID
    image_sha: str
    token_sha256: str
    title: str | None
    genre: str
    created_by: UUID


class ShareRepository:
    """Share links of a family's world cover; only token hashes are stored."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def active(self, family_id: UUID) -> list[ActiveShare]:
        """Every active link of the family, whatever world version it pins."""
        rows = await self._conn.execute(
            text(
                "SELECT id, world_job_id, title, genre FROM world_shares"
                " WHERE family_id = :fid AND revoked_at IS NULL"
            ),
            {"fid": family_id},
        )
        return [ActiveShare(r.id, r.world_job_id, r.title, r.genre) for r in rows]

    async def count_recent(self, family_id: UUID, window: timedelta) -> int:
        row = await self._conn.execute(
            text(
                "SELECT count(*) FROM world_shares WHERE family_id = :fid"
                " AND created_at > now() - CAST(:window AS interval)"
            ),
            {"fid": family_id, "window": window},
        )
        return row.scalar_one()

    async def create(self, new: NewShare) -> None:
        await self._conn.execute(
            text(
                "INSERT INTO world_shares (id, family_id, world_job_id, image_sha, token_sha256,"
                " title, genre, created_by) VALUES (:id, :fid, :job, :sha, :tok, :title, :genre,"
                " :by)"
            ),
            {
                "id": new.id,
                "fid": new.family_id,
                "job": new.world_job_id,
                "sha": new.image_sha,
                "tok": new.token_sha256,
                "title": new.title,
                "genre": new.genre,
                "by": new.created_by,
            },
        )

    async def revoke_all(self, family_id: UUID) -> int:
        """Revoke every active link; return how many there were."""
        result = await self._conn.execute(
            text(
                "UPDATE world_shares SET revoked_at = now()"
                " WHERE family_id = :fid AND revoked_at IS NULL"
            ),
            {"fid": family_id},
        )
        return result.rowcount

    async def by_token(self, token_sha256: str) -> Share | None:
        """The active link with this token hash and the counters of its own family only."""
        row = (
            await self._conn.execute(
                text(
                    "SELECT s.id, s.title, s.genre," + _STORY_COUNTS + " FROM world_shares s"
                    " WHERE s.token_sha256 = :tok AND s.revoked_at IS NULL"
                ),
                {"tok": token_sha256},
            )
        ).first()
        if row is None:
            return None
        return Share(row.id, row.title, row.genre, StoryCounts(row.quests_done, row.chapters))

    async def counts(self, family_id: UUID) -> StoryCounts:
        """The family's counters, from the same SQL as the public card."""
        row = (
            await self._conn.execute(
                text("SELECT" + _STORY_COUNTS + " FROM (SELECT CAST(:fid AS uuid) AS family_id) s"),
                {"fid": family_id},
            )
        ).one()
        return StoryCounts(row.quests_done, row.chapters)

    async def cover_bytes(self, token_sha256: str) -> bytes | None:
        """The cover pinned by an active link, None for anything else."""
        row = await self._conn.execute(
            text(
                "SELECT i.bytes FROM world_shares s JOIN world_images i"
                " ON i.family_id = s.family_id AND i.sha256 = s.image_sha AND i.status = 'ready'"
                " WHERE s.token_sha256 = :tok AND s.revoked_at IS NULL LIMIT 1"
            ),
            {"tok": token_sha256},
        )
        return row.scalar_one_or_none()
