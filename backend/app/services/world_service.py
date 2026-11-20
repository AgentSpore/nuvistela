from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

from app.domain.adventure import QuestDraft
from app.domain.errors import Conflict, Forbidden, NotFound, RateLimited
from app.domain.family import Member, Role
from app.repositories.family_repository import FamilyRepository
from app.repositories.image_repository import CoverState, ImageRepository
from app.repositories.job_repository import JobRepository
from app.repositories.world_repository import StoredWorld, WorldRepository, WorldStatus
from app.services.adventure_fallback import fallback_world_and_quest


@dataclass(frozen=True)
class WorldForm:
    """The questionnaire. genre None = regenerate with the stored genre and interests."""

    genre: str | None = None
    custom_genre: str | None = None
    interests: dict[UUID, tuple[str, ...]] = field(default_factory=dict)


class WorldService:
    DAILY_LIMIT = 3  # requests (first + regenerations) per family in a rolling 24 hours

    def __init__(
        self,
        families: FamilyRepository,
        worlds: WorldRepository,
        jobs: JobRepository,
        images: ImageRepository,
        world_available: bool = True,
    ):
        self._families, self._worlds, self._jobs = families, worlds, jobs
        self._images = images
        self._world_available = world_available  # a worker can process world jobs

    async def get(self, actor: Member, family_id: UUID) -> StoredWorld:
        stored = await self._worlds.get(family_id) if actor.family_id == family_id else None
        if stored is None:
            raise NotFound("world not found")
        return stored

    async def cover(self, family_id: UUID) -> CoverState | None:
        """The cover of the family's current world. Callers check ownership."""
        return await self._images.cover_state(family_id)

    async def cover_growing(self, family_id: UUID) -> bool:
        """True while a new cover for the current world is on its way."""
        return await self._images.growth_pending(family_id)

    async def status(self, family_id: UUID) -> WorldStatus | None:
        """The family's world status, None before the first request. Callers check ownership."""
        stored = await self._worlds.get(family_id)
        return None if stored is None else stored.status

    async def request(self, actor: Member, family_id: UUID, form: WorldForm) -> StoredWorld:
        """Queue world generation; the model is called by the worker, not by this request."""
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can create the world")
        if not self._world_available:
            raise Conflict("world generation is not available on this server")
        await self._families.lock_family(family_id)  # makes the count below race-free
        previous = await self._worlds.get(family_id)
        genre, custom = form.genre, form.custom_genre
        if genre is None:
            if previous is None:
                raise NotFound("world not found")
            genre, custom = previous.genre, previous.custom_genre
        window = timedelta(days=1)
        if await self._jobs.count_recent("world", family_id, window) >= self.DAILY_LIMIT:
            raise RateLimited("the world was requested too often today, try again tomorrow")
        await self._apply_interests(family_id, form.interests)
        family = await self._families.get_family(family_id)
        # Ids only: names and interests are read by the worker, not kept in the queue.
        payload = {
            "genre": genre,
            "custom_genre": custom,
            "locale": family.locale if family else "ru",
        }
        job_id = await self._jobs.enqueue("world", family_id, payload)
        await self._worlds.request(family_id, genre, custom, job_id)
        return StoredWorld("pending", genre, custom, previous.world if previous else None)

    async def store_fallback(self, actor: Member, family_id: UUID, form: WorldForm) -> QuestDraft:
        """Store the fallback world at once, for a deployment that cannot generate one.

        Returns the world's quest 1. No job is queued: nothing would process it.
        """
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can create the world")
        await self._apply_interests(family_id, form.interests)
        family = await self._families.get_family(family_id)
        members = await self._families.list_members(family_id)
        genre = form.genre or "fairy_tale"
        locale = family.locale if family else "ru"
        world, draft = fallback_world_and_quest(genre, locale, [m.id for m in members])
        job_id = uuid4()  # the writer key of the row; no queue entry carries it
        await self._worlds.request(family_id, genre, form.custom_genre, job_id)
        await self._worlds.save(family_id, "fallback", world, job_id)
        return draft

    async def _apply_interests(
        self, family_id: UUID, interests: dict[UUID, tuple[str, ...]]
    ) -> None:
        known = {m.id for m in await self._families.list_members(family_id)}
        if not set(interests) <= known:
            raise NotFound("member not found")
        for member_id, values in interests.items():
            await self._families.set_interests(member_id, values)
