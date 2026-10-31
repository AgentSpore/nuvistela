from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.family import AgeBand, Family, Member, NewMember, Role

_MEMBER_COLS = "id, family_id, display_name, age_band, role, interests, created_at"


class FamilyRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    @staticmethod
    def _member(row: Row) -> Member:
        return Member(
            id=row.id,
            family_id=row.family_id,
            display_name=row.display_name,
            age_band=AgeBand(row.age_band),
            role=Role(row.role),
            interests=tuple(row.interests),
            created_at=row.created_at,
        )

    async def create_family(self, title: str, locale: str) -> Family:
        row = (
            await self._conn.execute(
                text(
                    "INSERT INTO families (title, locale) VALUES (:title, :locale)"
                    " RETURNING id, title, locale, created_at"
                ),
                {"title": title, "locale": locale},
            )
        ).one()
        return Family(row.id, row.title, row.locale, row.created_at)

    async def add_member(self, family_id: UUID, new: NewMember, token_hash: str) -> Member:
        row = (
            await self._conn.execute(
                text(
                    "INSERT INTO members"
                    " (family_id, display_name, age_band, role, interests, invite_token_hash)"
                    " VALUES (:family_id, :name, :age_band, :role,"
                    " CAST(:interests AS text[]), :hash)"
                    f" RETURNING {_MEMBER_COLS}"
                ),
                {
                    "family_id": family_id,
                    "name": new.display_name,
                    "age_band": new.age_band.value,
                    "role": new.role.value,
                    "interests": list(new.interests),
                    "hash": token_hash,
                },
            )
        ).one()
        return self._member(row)

    async def get_member(self, member_id: UUID) -> Member | None:
        row = (
            await self._conn.execute(
                text(f"SELECT {_MEMBER_COLS} FROM members WHERE id = :id"), {"id": member_id}
            )
        ).first()
        return self._member(row) if row else None

    async def get_member_by_token_hash(self, token_hash: str) -> Member | None:
        row = (
            await self._conn.execute(
                text(f"SELECT {_MEMBER_COLS} FROM members WHERE invite_token_hash = :hash"),
                {"hash": token_hash},
            )
        ).first()
        return self._member(row) if row else None

    async def set_token_hash(self, member_id: UUID, token_hash: str) -> None:
        await self._conn.execute(
            text("UPDATE members SET invite_token_hash = :hash WHERE id = :id"),
            {"hash": token_hash, "id": member_id},
        )
