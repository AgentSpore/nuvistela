import hashlib
import hmac
import re
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from pydantic import SecretStr

from app.domain.errors import Conflict, Forbidden, NotFound, RateLimited
from app.domain.family import Member, Role
from app.domain.world import GENRES, description_names, title_names_nobody
from app.repositories.family_repository import FamilyRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.share_repository import NewShare, Share, ShareRepository, StoryCounts
from app.repositories.world_repository import StoredWorld, WorldRepository

_TOKEN = re.compile(r"[A-Za-z0-9_-]{22}")


def _genre_key(genre: str) -> str:
    """A custom genre's free text is never published: unknown keys become `custom`."""
    return genre if genre in GENRES else "custom"


@dataclass(frozen=True)
class SharedLink:
    token: str
    created: bool


@dataclass(frozen=True)
class ShareStatus:
    title: str | None
    genre: str
    token: str | None
    other_active: bool  # an active link exists that `token` does not name: it can still be revoked
    counts: StoryCounts  # what the public card shows next to the title


class ShareService:
    DAILY_LIMIT = 10  # new links per family in a rolling 24 hours

    def __init__(
        self,
        families: FamilyRepository,
        worlds: WorldRepository,
        images: ImageRepository,
        shares: ShareRepository,
        key: SecretStr | None,
    ):
        self._families, self._worlds, self._images = families, worlds, images
        self._shares, self._key = shares, key

    def _token(self, share_id: UUID) -> str:
        """128 bits only the key holder can compute; the database keeps its hash alone."""
        assert self._key is not None
        mac = hmac.new(self._key.get_secret_value().encode(), share_id.bytes, hashlib.sha256)
        return urlsafe_b64encode(mac.digest()[:16]).decode().rstrip("=")

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _owned_by_adult(actor: Member, family_id: UUID) -> None:
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can share the world")

    async def _public_title(self, family_id: UUID, stored: StoredWorld) -> str | None:
        """The title as strangers see it: dropped when it names a member or a name of the
        player's own world description (a pet, a place)."""
        assert stored.world is not None
        names = [m.display_name for m in await self._families.list_members(family_id)]
        description = stored.custom_genre or ""
        names += description_names(description)
        public = title_names_nobody(stored.world.title, names, description)
        return stored.world.title if public else None

    async def status(self, actor: Member, family_id: UUID) -> ShareStatus:
        """The active link's stored card, else what a new link would show."""
        self._owned_by_adult(actor, family_id)
        stored = await self._worlds.get(family_id)
        job_id = await self._worlds.current_job_id(family_id)
        if job_id is None or stored is None or stored.world is None or stored.status != "ready":
            raise Conflict("the world is not ready")
        active = await self._shares.active(family_id)
        current = next((s for s in active if s.world_job_id == job_id), None)
        counts = await self._shares.counts(family_id)
        if current is None:
            title = await self._public_title(family_id, stored)
            return ShareStatus(title, _genre_key(stored.genre), None, bool(active), counts)
        token = self._token(current.id) if self._key is not None else None
        other = len(active) > (token is not None)
        return ShareStatus(current.title, current.genre, token, other, counts)

    async def create(self, actor: Member, family_id: UUID) -> SharedLink:
        """The active link of the current world, made on first request."""
        self._owned_by_adult(actor, family_id)
        if self._key is None:
            raise Conflict("sharing is not available on this server")
        await self._families.lock_family(family_id)
        job_id = await self._worlds.current_job_id(family_id)
        stored = await self._worlds.get(family_id)
        cover = await self._images.cover_state(family_id)
        if job_id is None or stored is None or stored.world is None or stored.status != "ready":
            raise Conflict("the world is not ready")
        if cover is None or cover.status != "ready" or cover.sha is None:
            raise Conflict("the world has no cover to share")
        active = await self._shares.active(family_id)
        if current := next((s for s in active if s.world_job_id == job_id), None):
            return SharedLink(self._token(current.id), created=False)
        if await self._shares.count_recent(family_id, timedelta(days=1)) >= self.DAILY_LIMIT:
            raise RateLimited("too many links today, try again tomorrow")
        title = await self._public_title(family_id, stored)
        share_id = uuid4()
        token = self._token(share_id)
        genre = _genre_key(stored.genre)
        await self._shares.create(
            NewShare(
                share_id, family_id, job_id, cover.sha, self._hash(token), title, genre, actor.id
            )
        )
        return SharedLink(token, created=True)

    async def revoke(self, actor: Member, family_id: UUID) -> bool:
        """Revoke the family's links; False when none was active."""
        self._owned_by_adult(actor, family_id)
        await self._families.lock_family(family_id)
        return await self._shares.revoke_all(family_id) > 0

    async def public(self, token: str) -> Share:
        """The active link's card; one NotFound for unknown, revoked and malformed tokens."""
        share = await self._shares.by_token(self._hash(token)) if _TOKEN.fullmatch(token) else None
        if share is None:
            raise NotFound("not found")
        return share

    async def cover(self, token: str) -> bytes:
        data = (
            await self._shares.cover_bytes(self._hash(token)) if _TOKEN.fullmatch(token) else None
        )
        if data is None:
            raise NotFound("not found")
        return data
