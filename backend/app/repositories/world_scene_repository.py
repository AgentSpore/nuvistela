import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

SceneStatus = Literal["pending", "ready", "failed"]


@dataclass(frozen=True)
class SceneInfo:
    """One scene without its bytes; sha is set only when ready."""

    world_job_id: UUID
    status: SceneStatus
    sha: str | None


class WorldSceneRepository:
    """3D scenes of a family's worlds kept in Postgres."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create_pending(self, family_id: UUID, world_job_id: UUID) -> bool:
        """Order the scene of a world version; False when it was already ordered."""
        result = await self._conn.execute(
            text(
                "INSERT INTO world_scenes (family_id, world_job_id) VALUES (:fid, :job)"
                " ON CONFLICT (family_id, world_job_id) DO NOTHING"
            ),
            {"fid": family_id, "job": world_job_id},
        )
        return result.rowcount == 1

    async def mark_ready(
        self, family_id: UUID, world_job_id: UUID, spz: bytes, panorama: bytes
    ) -> bool:
        """Store the bytes and the spz sha256; False when the row is missing or not pending."""
        result = await self._conn.execute(
            text(
                "UPDATE world_scenes SET status = 'ready', sha256 = :sha, spz = :spz,"
                " panorama = :panorama, updated_at = now()"
                " WHERE family_id = :fid AND world_job_id = :job AND status = 'pending'"
            ),
            {
                "fid": family_id,
                "job": world_job_id,
                "sha": hashlib.sha256(spz).hexdigest(),
                "spz": spz,
                "panorama": panorama,
            },
        )
        return result.rowcount == 1

    async def mark_failed(self, family_id: UUID, world_job_id: UUID) -> bool:
        """False when the row is missing or not pending."""
        result = await self._conn.execute(
            text(
                "UPDATE world_scenes SET status = 'failed', updated_at = now()"
                " WHERE family_id = :fid AND world_job_id = :job AND status = 'pending'"
            ),
            {"fid": family_id, "job": world_job_id},
        )
        return result.rowcount == 1

    async def list_for_family(self, family_id: UUID) -> list[SceneInfo]:
        """Scenes of the family, newest first. Never selects the byte columns."""
        rows = await self._conn.execute(
            text(
                "SELECT world_job_id, status, sha256 FROM world_scenes"
                " WHERE family_id = :fid ORDER BY created_at DESC"
            ),
            {"fid": family_id},
        )
        return [SceneInfo(r.world_job_id, r.status, r.sha256) for r in rows]

    async def ready_spz(self, family_id: UUID, sha: str) -> bytes | None:
        """The spz of a ready scene of this family, None for anything else."""
        row = await self._conn.execute(
            text(
                "SELECT spz FROM world_scenes"
                " WHERE family_id = :fid AND sha256 = :sha AND status = 'ready' LIMIT 1"
            ),
            {"fid": family_id, "sha": sha},
        )
        return row.scalar_one_or_none()

    async def current_state(self, family_id: UUID) -> SceneInfo | None:
        """The scene of the family's current world, None when none was ordered for it."""
        row = (
            await self._conn.execute(
                text(
                    "SELECT s.world_job_id, s.status, s.sha256 FROM world_scenes s"
                    " JOIN worlds w ON w.family_id = s.family_id AND w.job_id = s.world_job_id"
                    " WHERE s.family_id = :fid"
                ),
                {"fid": family_id},
            )
        ).first()
        return None if row is None else SceneInfo(row.world_job_id, row.status, row.sha256)

    async def pending_prompt(self, family_id: UUID, world_job_id: UUID) -> str | None:
        """The cover prompt to build the scene from; None unless the scene is pending and its
        world is still current."""
        row = await self._conn.execute(
            text(
                "SELECT i.prompt FROM world_scenes s"
                " JOIN world_images i ON i.family_id = s.family_id"
                "   AND i.world_job_id = s.world_job_id AND i.kind = 'cover'"
                " JOIN worlds w ON w.family_id = s.family_id AND w.job_id = s.world_job_id"
                " WHERE s.family_id = :fid AND s.world_job_id = :job"
                " AND s.status = 'pending' AND w.status = 'ready'"
            ),
            {"fid": family_id, "job": world_job_id},
        )
        return row.scalar_one_or_none()

    async def ready_panorama(self, family_id: UUID, sha: str) -> bytes | None:
        """The panorama of a ready scene (named by the sha of its spz) of this family."""
        row = await self._conn.execute(
            text(
                "SELECT panorama FROM world_scenes"
                " WHERE family_id = :fid AND sha256 = :sha AND status = 'ready' LIMIT 1"
            ),
            {"fid": family_id, "sha": sha},
        )
        return row.scalar_one_or_none()
