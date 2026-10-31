import hashlib
import secrets
from uuid import UUID

from app.domain.errors import Forbidden, NotFound, Unauthorized
from app.domain.family import AgeBand, Family, Member, NewMember, Role
from app.repositories.family_repository import FamilyRepository


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


class FamilyService:
    def __init__(self, repo: FamilyRepository) -> None:
        self._repo = repo

    async def create_family(
        self, title: str, locale: str, first_adult: str, interests: tuple[str, ...]
    ) -> tuple[Family, Member, str]:
        family = await self._repo.create_family(title, locale)
        token, token_hash = _new_token()
        adult = NewMember(first_adult, AgeBand.ADULT, Role.ADULT, interests)
        member = await self._repo.add_member(family.id, adult, token_hash)
        return family, member, token

    async def authenticate(self, token: str) -> Member:
        member = await self._repo.get_member_by_token_hash(hash_token(token))
        if member is None:
            raise Unauthorized
        return member

    async def add_member(
        self, actor: Member, family_id: UUID, new: NewMember
    ) -> tuple[Member, str]:
        if actor.family_id != family_id:
            raise NotFound
        if actor.role is not Role.ADULT:
            raise Forbidden
        token, token_hash = _new_token()
        return await self._repo.add_member(family_id, new, token_hash), token

    async def reissue_invite(self, actor: Member, member_id: UUID) -> str:
        target = await self._repo.get_member(member_id)
        if target is None or target.family_id != actor.family_id:
            raise NotFound
        if actor.role is not Role.ADULT:
            raise Forbidden
        token, token_hash = _new_token()
        await self._repo.set_token_hash(member_id, token_hash)
        return token
