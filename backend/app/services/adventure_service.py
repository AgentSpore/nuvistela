from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID

from app.domain.adventure import Adventure, Chapter
from app.domain.errors import Conflict, Forbidden, NotFound, RateLimited
from app.domain.family import Member, Role
from app.repositories.adventure_repository import AdventureRepository
from app.repositories.family_repository import FamilyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.world_repository import WorldStatus
from app.services.adventure_fallback import open_fallback_quest
from app.services.world_service import WorldForm, WorldService


@dataclass(frozen=True)
class AdventureView:
    world_status: WorldStatus | None
    adventure: Adventure


class AdventureService:
    RETRY_LIMIT = 3  # retries per family in a rolling 24 hours; first writes are not counted

    def __init__(
        self,
        families: FamilyRepository,
        adventures: AdventureRepository,
        jobs: JobRepository,
        worlds: WorldService,
        world_available: bool = True,
    ):
        self._families, self._adventures, self._jobs = families, adventures, jobs
        self._worlds = worlds
        self._world_available = world_available  # a worker can process world jobs

    async def start(self, actor: Member, family_id: UUID, form: WorldForm) -> AdventureView:
        """Queue the world on the first start; the world worker opens quest 1 with the result.

        Until then the state is world `pending` with no quest. Later calls return the current
        state. A template quest is opened here only when a finished world left the family with
        none, or when the latest chapter is delayed.
        """
        if actor.family_id != family_id:
            raise NotFound("family not found")
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can start the adventure")
        await self._families.lock_family(family_id)
        current = await self._adventures.get_adventure(family_id)
        if current.quest is not None:
            return await self.get(actor, family_id)
        if not current.chapters:
            world_status = await self._worlds.status(family_id)
            if world_status is None and self._world_available:
                await self._worlds.request(actor, family_id, form)
            elif not self._world_available and world_status in (None, "pending"):
                # Nothing would process a queued world either: store the fallback over it.
                draft = await self._worlds.store_fallback(actor, family_id, form)
                await self._adventures.open_first_quest(family_id, None, draft)
            elif world_status != "pending":
                await self._open_template(actor, family_id)
        elif current.chapters[-1].status.startswith("delayed"):
            await self._open_template(actor, family_id)
        return await self.get(actor, family_id)

    async def _open_template(self, actor: Member, family_id: UUID) -> None:
        family = await self._families.get_family(family_id)
        locale = family.locale if family else "ru"
        await open_fallback_quest(self._adventures, family_id, actor.id, locale)

    async def get(self, actor: Member, family_id: UUID) -> AdventureView:
        """The single source of the adventure screen: world status, open quest, chapters."""
        if actor.family_id != family_id:
            raise NotFound("family not found")
        world = await self._worlds.status(family_id)
        return AdventureView(world, await self._adventures.get_adventure(family_id))

    async def done(
        self, actor: Member, quest_id: UUID, note: str | None, idem_key: str | None
    ) -> Chapter:
        """Mark the quest done once; only the first call queues the chapter and its job."""
        quest = await self._adventures.lock_quest(quest_id, actor.family_id)
        if quest is None:
            raise NotFound("quest not found")
        event, created = await self._adventures.mark_done(
            quest.id, actor.family_id, actor.id, note, idem_key
        )
        if event.quest_id != quest.id:
            raise Conflict("the idempotency key belongs to another quest")
        if created:
            job_id = await self._enqueue_chapter(actor.family_id, quest.id)
            chapter, _ = await self._adventures.create_chapter(quest.id, job_id)
        else:
            chapter = await self._adventures.chapter_of_quest(quest.id)
        if chapter is None:
            raise NotFound("chapter not found")
        return chapter

    async def retry(self, actor: Member, chapter_id: UUID) -> Chapter:
        """Requeue a delayed chapter with a fresh job, within the daily limit (adults only)."""
        if actor.role is not Role.ADULT:
            raise Forbidden("only adults can retry a chapter")
        await self._families.lock_family(actor.family_id)
        chapter = await self._adventures.get_chapter(chapter_id, actor.family_id)
        if chapter is None:
            raise NotFound("chapter not found")
        if chapter.status not in ("delayed_model", "delayed_budget"):
            raise Conflict("only a delayed chapter can be retried")
        recent = await self._adventures.count_recent_retries(actor.family_id, timedelta(days=1))
        if recent >= self.RETRY_LIMIT:
            raise RateLimited("the chapter was retried too often today, try again tomorrow")
        job_id = await self._enqueue_chapter(actor.family_id, chapter.quest_id, retry=True)
        if not await self._adventures.requeue_chapter(chapter.id, job_id):
            # The request rolls back on Conflict, so the job queued above does not survive.
            current = await self._adventures.get_chapter(chapter.id, actor.family_id)
            raise Conflict(f"the chapter is {current.status if current else 'gone'}, not delayed")
        return replace(chapter, status="queued", job_id=job_id)

    async def _enqueue_chapter(self, family_id: UUID, quest_id: UUID, retry: bool = False) -> UUID:
        family = await self._families.get_family(family_id)
        # Ids only: the member's note stays in quest_events, not in the queue.
        payload: dict = {"quest_id": str(quest_id), "locale": family.locale if family else "ru"}
        if retry:
            payload["retry"] = True
        return await self._jobs.enqueue("chapter", family_id, payload)
