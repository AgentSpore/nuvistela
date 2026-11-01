from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from app.domain.errors import Forbidden, NotFound, RateLimited
from app.domain.family import Member, Role
from app.repositories.family_repository import FamilyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.world_repository import StoredWorld, WorldRepository


@dataclass(frozen=True)
class WorldForm:
    """The questionnaire. genre None = regenerate with the stored genre and interests."""

    genre: str | None = None
    custom_genre: str | None = None
    interests: dict[UUID, tuple[str, ...]] = field(default_factory=dict)


class WorldService:
    DAILY_LIMIT = 3  # requests (first + regenerations) per family in a rolling 24 hours

    def __init__(self, families: FamilyRepository, worlds: WorldRepository, jobs: JobRepository):
        self._families, self._worlds, self._jobs = families, worlds, jobs

    async def get(self, actor: Member, family_id: UUID) -> StoredWorld:
        stored = await self._worlds.get(family_id) if actor.family_id == family_id else None
        if stored is None:
            raise NotFound("world not found")
        return stored

    async def request(self, actor: Member, family_id: UUID, form: WorldForm) -> StoredWorld:
        """Queue world generation; the model is called by the worker, not by this request."""
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can create the world")
        previous = await self._worlds.get(family_id)
        genre, custom = form.genre, form.custom_genre
        if genre is None:
            if previous is None:
                raise NotFound("world not found")
            genre, custom = previous.genre, previous.custom_genre
        if await self._jobs.count_recent("world", family_id, timedelta(days=1)) >= self.DAILY_LIMIT:
            raise RateLimited("the world was requested too often today, try again tomorrow")
        members = await self._apply_interests(family_id, form.interests)
        await self._worlds.request(family_id, genre, custom)
        family = await self._families.get_family(family_id)
        await self._jobs.enqueue(
            "world",
            family_id,
            {
                "genre": genre,
                "custom_genre": custom,
                "locale": family.locale if family else "ru",
                "members": [
                    {"member_id": str(m.id), "age_band": m.age_band.value, "interests": m.interests}
                    for m in members
                ],
                "private": [m.display_name for m in members],
            },
        )
        return StoredWorld("pending", genre, custom, previous.world if previous else None)

    async def _apply_interests(
        self, family_id: UUID, interests: dict[UUID, tuple[str, ...]]
    ) -> list[Member]:
        members = await self._families.list_members(family_id)
        known = {m.id for m in members}
        if not set(interests) <= known:
            raise NotFound("member not found")
        for member_id, values in interests.items():
            await self._families.set_interests(member_id, values)
        return await self._families.list_members(family_id) if interests else members
