import hashlib
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.errors import AdmissionRefused, Forbidden, NotFound, Unauthorized
from app.domain.family import PRIVACY_POLICY_VERSION, AgeBand, Family, Member, NewMember, Role
from app.domain.funnel import EventKind
from app.repositories.family_repository import FamilyRepository
from app.services.funnel_service import FunnelService


class FamilyService:
    INVITE_TTL = timedelta(days=7)
    SESSION_TTL = timedelta(days=365)

    def __init__(self, repo: FamilyRepository, funnel: FunnelService) -> None:
        self._repo = repo
        self._funnel = funnel

    @staticmethod
    def hash_token(token: str) -> str:
        """Return the sha256 hex digest stored in place of the raw token."""
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def _new_token(cls) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        return token, cls.hash_token(token)

    @classmethod
    def _invite_expiry(cls) -> datetime:
        return datetime.now(UTC) + cls.INVITE_TTL

    async def _open_session(self, member_id: UUID) -> str:
        session, session_hash = self._new_token()
        expires = datetime.now(UTC) + self.SESSION_TTL
        await self._repo.create_session(member_id, session_hash, expires)
        return session

    async def create_family(
        self, title: str, locale: str, first_adult: str, interests: tuple[str, ...]
    ) -> tuple[Family, Member, str, str]:
        """Create the family and its first adult; return (family, adult, invite, session)."""
        family = await self._repo.create_family(title, locale, PRIVACY_POLICY_VERSION)
        invite, invite_hash = self._new_token()
        adult = NewMember(first_adult, AgeBand.ADULT, Role.ADULT, interests)
        member = await self._repo.add_member(family.id, adult, invite_hash, self._invite_expiry())
        await self._repo.set_owner(family.id, member.id)
        await self._funnel.record_event(EventKind.FAMILY_CREATED, family.id, member.id)
        return family, replace(member, is_owner=True), invite, await self._open_session(member.id)

    async def require_daily_capacity(self, max_per_day: int, erased_today: int = 0) -> None:
        """Refuse a new family once `max_per_day` were created this UTC day (0 = no limit).

        Erased families of today still hold their place: `erased_today` is added to the live rows.
        """
        if not max_per_day:
            return
        midnight = self._utc_midnight()
        if await self._repo.count_families_since(midnight) + erased_today >= max_per_day:
            raise AdmissionRefused("daily_full")

    async def delete_family(self, actor: Member, family_id: UUID) -> bool:
        """Erase the family and all its data; only its owner may.

        Returns True when the family had been created in the current UTC day.
        """
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if not actor.is_owner:
            raise Forbidden("only the family owner can delete the family")
        family = await self._repo.get_family(family_id)
        await self._repo.delete_family(family_id)
        return family is not None and family.created_at >= self._utc_midnight()

    @staticmethod
    def _utc_midnight() -> datetime:
        return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    async def accept_invite(self, invite: str) -> tuple[Member, str]:
        """Consume a single-use invite; return the member and a new session token."""
        member = await self._repo.consume_invite(self.hash_token(invite))
        if member is None:
            raise Unauthorized("invalid or expired invite")
        return member, await self._open_session(member.id)

    async def authenticate(self, session: str) -> Member:
        member = await self._repo.get_member_by_session_hash(self.hash_token(session))
        if member is None:
            raise Unauthorized("not authenticated")
        return member

    async def add_member(
        self, actor: Member, family_id: UUID, new: NewMember
    ) -> tuple[Member, str]:
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can add members")
        invite, invite_hash = self._new_token()
        member = await self._repo.add_member(family_id, new, invite_hash, self._invite_expiry())
        return member, invite

    async def list_members(self, actor: Member, family_id: UUID) -> list[Member]:
        if actor.family_id != family_id:
            raise NotFound("family not found")
        return await self._repo.list_members(family_id)

    async def family_locale(self, family_id: UUID) -> str:
        family = await self._repo.get_family(family_id)
        return family.locale if family else "ru"

    async def reissue_invite(self, actor: Member, member_id: UUID) -> str:
        target = await self._repo.get_member(member_id)
        if target is None or target.family_id != actor.family_id:
            raise NotFound("member not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can reissue invites")
        # Owner decision 01.11: the family owner reissues for any member; other adults only for
        # children and themselves.
        if target.role is Role.ADULT and target.id != actor.id and not actor.is_owner:
            raise Forbidden("cannot reissue another adult's invite")
        invite, invite_hash = self._new_token()
        await self._repo.replace_invite(member_id, invite_hash, self._invite_expiry())
        return invite
