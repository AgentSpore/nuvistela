from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.family import AgeBand, Family, Member, NewMember, Role

_MEMBER_COLS = (
    "id, family_id, display_name, age_band, role, interests, created_at,"
    " EXISTS (SELECT 1 FROM families f WHERE f.owner_member_id = members.id) AS is_owner"
)


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
            is_owner=row.is_owner,
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

    async def add_member(
        self, family_id: UUID, new: NewMember, invite_hash: str, invite_expires_at: datetime
    ) -> Member:
        row = (
            await self._conn.execute(
                text(
                    "INSERT INTO members (family_id, display_name, age_band, role, interests,"
                    " invite_token_hash, invite_expires_at)"
                    " VALUES (:family_id, :name, :age_band, :role, CAST(:interests AS text[]),"
                    " :hash, :expires)"
                    f" RETURNING {_MEMBER_COLS}"
                ),
                {
                    "family_id": family_id,
                    "name": new.display_name,
                    "age_band": new.age_band.value,
                    "role": new.role.value,
                    "interests": list(new.interests),
                    "hash": invite_hash,
                    "expires": invite_expires_at,
                },
            )
        ).one()
        return self._member(row)

    async def set_owner(self, family_id: UUID, member_id: UUID) -> None:
        await self._conn.execute(
            text("UPDATE families SET owner_member_id = :member WHERE id = :id"),
            {"member": member_id, "id": family_id},
        )

    async def get_family(self, family_id: UUID) -> Family | None:
        row = (
            await self._conn.execute(
                text("SELECT id, title, locale, created_at FROM families WHERE id = :id"),
                {"id": family_id},
            )
        ).first()
        return Family(row.id, row.title, row.locale, row.created_at) if row else None

    async def get_member(self, member_id: UUID) -> Member | None:
        row = (
            await self._conn.execute(
                text(f"SELECT {_MEMBER_COLS} FROM members WHERE id = :id"), {"id": member_id}
            )
        ).first()
        return self._member(row) if row else None

    async def list_members(self, family_id: UUID) -> list[Member]:
        rows = await self._conn.execute(
            text(
                f"SELECT {_MEMBER_COLS} FROM members WHERE family_id = :id ORDER BY created_at, id"
            ),
            {"id": family_id},
        )
        return [self._member(r) for r in rows]

    async def consume_invite(self, invite_hash: str) -> Member | None:
        """Clear a live invite and return its member; None if unknown, used or expired."""
        row = (
            await self._conn.execute(
                text(
                    "UPDATE members SET invite_token_hash = NULL, invite_expires_at = NULL"
                    " WHERE invite_token_hash = :hash AND invite_expires_at > now()"
                    f" RETURNING {_MEMBER_COLS}"
                ),
                {"hash": invite_hash},
            )
        ).first()
        return self._member(row) if row else None

    async def create_session(self, member_id: UUID, token_hash: str, expires_at: datetime) -> None:
        """Insert a session and drop the member's expired ones."""
        await self._conn.execute(
            text("DELETE FROM sessions WHERE member_id = :id AND expires_at <= now()"),
            {"id": member_id},
        )
        await self._conn.execute(
            text(
                "INSERT INTO sessions (member_id, token_hash, expires_at)"
                " VALUES (:member_id, :hash, :expires)"
            ),
            {"member_id": member_id, "hash": token_hash, "expires": expires_at},
        )

    async def get_member_by_session_hash(self, token_hash: str) -> Member | None:
        row = (
            await self._conn.execute(
                text(
                    "SELECT m.id, m.family_id, m.display_name, m.age_band, m.role, m.interests,"
                    " m.created_at,"
                    " EXISTS (SELECT 1 FROM families f WHERE f.owner_member_id = m.id) AS is_owner"
                    " FROM sessions s JOIN members m ON m.id = s.member_id"
                    " WHERE s.token_hash = :hash AND s.expires_at > now()"
                ),
                {"hash": token_hash},
            )
        ).first()
        return self._member(row) if row else None

    async def replace_invite(
        self, member_id: UUID, invite_hash: str, invite_expires_at: datetime
    ) -> None:
        """Set a new invite and drop every session of the member."""
        await self._conn.execute(
            text(
                "UPDATE members SET invite_token_hash = :hash, invite_expires_at = :expires"
                " WHERE id = :id"
            ),
            {"hash": invite_hash, "expires": invite_expires_at, "id": member_id},
        )
        await self._conn.execute(
            text("DELETE FROM sessions WHERE member_id = :id"), {"id": member_id}
        )
