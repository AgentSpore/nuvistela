from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.world import World

WorldStatus = Literal["pending", "ready", "fallback"]


@dataclass(frozen=True)
class StoredWorld:
    status: WorldStatus
    genre: str
    custom_genre: str | None
    world: World | None


class WorldRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def request(self, family_id: UUID, genre: str, custom_genre: str | None) -> None:
        """Mark the family's world pending; a previous world stays readable until replaced."""
        await self._conn.execute(
            text(
                "INSERT INTO worlds (family_id, status, genre, custom_genre)"
                " VALUES (:fid, 'pending', :genre, :custom)"
                " ON CONFLICT (family_id) DO UPDATE SET status = 'pending', genre = :genre,"
                " custom_genre = :custom, updated_at = now()"
            ),
            {"fid": family_id, "genre": genre, "custom": custom_genre},
        )

    async def get(self, family_id: UUID) -> StoredWorld | None:
        row = (
            await self._conn.execute(
                text("SELECT status, genre, custom_genre, world FROM worlds WHERE family_id = :f"),
                {"f": family_id},
            )
        ).first()
        if row is None:
            return None
        world = World.model_validate(row.world) if row.world is not None else None
        return StoredWorld(row.status, row.genre, row.custom_genre, world)

    async def save(self, family_id: UUID, status: WorldStatus, world: World) -> None:
        await self._conn.execute(
            text(
                "UPDATE worlds SET status = :status, world = CAST(:world AS jsonb),"
                " updated_at = now() WHERE family_id = :fid"
            ),
            {"fid": family_id, "status": status, "world": world.model_dump_json()},
        )
