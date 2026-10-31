import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.errors import Forbidden, NotFound
from app.domain.family import Member, Role
from app.repositories.link_repository import LinkRepository
from app.services.family_service import FamilyService

# No 0/O/1/I/L: the code is read off a screen and typed into a chat.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 8


class TelegramLinkService:
    CODE_TTL = timedelta(minutes=10)

    def __init__(self, repo: LinkRepository) -> None:
        self._repo = repo

    @staticmethod
    def _hash(code: str) -> str:
        return FamilyService.hash_token(code.strip().upper())

    async def issue_code(self, actor: Member, family_id: UUID) -> tuple[str, datetime]:
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can link a chat")
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))
        expires = datetime.now(UTC) + self.CODE_TTL
        await self._repo.create_code(actor.id, self._hash(code), expires)
        return code, expires

    async def link_chat(self, chat_id: int, code: str) -> bool:
        """Consume the code and bind the chat in one transaction; False for a bad code."""
        family_id = await self._repo.consume_code(self._hash(code))
        if family_id is None:
            return False
        await self._repo.bind_chat(chat_id, family_id)
        return True
