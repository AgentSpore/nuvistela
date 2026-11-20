"""Polls the queue for chapter jobs: reserve money, write the chapter, store it with the quest."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.agent.chapter_writer import ChapterSpec, ChapterWriter
from app.agent.money_gate import MoneyGate
from app.agent.name_mask import mask_names
from app.core.config import Settings
from app.domain.adventure import (
    Chapter,
    ChapterStatus,
    ChapterText,
    QuestContext,
    QuestDraft,
    beat_of,
    growth_cover_milestone,
)
from app.domain.family import AgeBand
from app.domain.world import description_names
from app.repositories.adventure_repository import AdventureRepository
from app.repositories.family_repository import FamilyRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.job_repository import Job, JobRepository
from app.repositories.world_repository import WorldRepository
from app.services.adventure_fallback import open_fallback_quest
from app.services.cover_prompt import GrowthStory, growth_cover_prompt

logger = logging.getLogger(__name__)
MODEL_RETRY_IN = timedelta(hours=1)  # when the delayed_model chapter is next due
MAX_AUTO_JOBS = 3  # automatic resumes per chapter; after that only the retry button


@dataclass(frozen=True)
class _Work:
    chapter: Chapter
    quest: QuestContext
    spec: ChapterSpec


def next_utc_midnight() -> datetime:
    """The Q13 day boundary: when a budget-delayed chapter is due again."""
    return datetime.combine(datetime.now(UTC).date() + timedelta(days=1), time(), tzinfo=UTC)


class ChapterWorker:
    def __init__(
        self,
        engine: AsyncEngine,
        writer: ChapterWriter,
        settings: Settings,
        gate: MoneyGate | None = None,
        notify: bool = False,
    ) -> None:
        self._engine, self._writer = engine, writer
        self._gate = gate or MoneyGate(engine, settings)
        self._settings = settings
        self._notify = notify  # a reminder worker runs: queue "chapter ready" jobs for it
        self._cover_on = bool(settings.image_model)

    async def run_once(self) -> bool:
        """Process one due job; False when the queue is empty. The model runs outside any tx."""
        async with self._engine.begin() as conn:
            await AdventureRepository(conn).requeue_due(MAX_AUTO_JOBS)
            job = await JobRepository(conn).claim(["chapter"])
            if job is None:
                return False
            work = await self._load(conn, job)
            if work is None:
                await JobRepository(conn).complete(job)
                logger.info("chapter job %s needs no model call", job.id)
                return True
            await AdventureRepository(conn).update_chapter_status(
                work.chapter.id, job.id, "writing"
            )
        if (
            job.attempts > self._settings.world_max_attempts
        ):  # claimed again and again: the worker keeps dying
            await self._fail(job, work, "AttemptsExceeded", final=True)
            return True
        micro = self._writer.worst_case(work.spec)
        reserved = await self._gate.reserve(
            job.family_id, job.id, job.attempts, micro, work.chapter.id
        )
        if reserved != "reserved":
            await self._skip(job, work, reserved)
            return True
        try:
            out, usage = await self._writer.write(work.spec)
        except Exception as exc:  # noqa: BLE001 (writer boundary: every failure must count as an attempt)
            # Class name only: provider text may carry request details. The reserve stays counted.
            logger.warning("chapter job failed: %s attempt=%s", type(exc).__name__, job.attempts)
            await self._fail(
                job,
                work,
                type(exc).__name__,
                final=job.attempts >= self._settings.world_max_attempts,
            )
            return True
        await self._store(job, work, out, self._writer.price.cost(usage))
        return True

    async def _load(self, conn, job: Job) -> _Work | None:
        """None when the job must not call the model: unknown quest, newer job, chapter ready."""
        adventures = AdventureRepository(conn)
        chapter = await adventures.chapter_of_quest(UUID(job.payload["quest_id"]))
        if chapter is None or chapter.job_id != job.id or chapter.status == "ready":
            return None
        quest = await adventures.quest_context(chapter.quest_id)
        if quest is None:
            return None
        stored = await WorldRepository(conn).get(job.family_id)
        world = stored.world if stored else None
        # A world still being generated must not stall the story: write without its description.
        summary = (
            f"{world.title}. {world.setting}. Tone: {world.tone}." if world else "not ready yet"
        )
        genre = stored.genre if stored else ""  # never the player's own text: `summary` carries it
        finished = await adventures.finished_quest_titles(chapter.quest_id)
        members = await FamilyRepository(conn).list_members(job.family_id)
        # INVARIANT(name-mask): a player's real name must never reach the model, chapters are
        # shared by link; without this the note prints a child's name in the story.
        note = (
            mask_names(quest.note, [m.display_name for m in members]) if quest.note else quest.note
        )
        spec = ChapterSpec(
            job.payload["locale"], genre or "unknown", summary, quest.previous_summary,
            quest.title, quest.description, note, quest.age_bands, chapter.seq,
            quest.reaction, quest.recent_kinds, quest.recent_skills, finished,
        )  # fmt: skip
        return _Work(chapter, quest, spec)

    async def _skip(self, job: Job, work: _Work, reason: str) -> None:
        """No model call: the cap is reached (due at UTC midnight) or the attempt repeats."""
        status, until = (
            ("delayed_budget", next_utc_midnight())
            if reason == "over_cap"
            else ("delayed_model", datetime.now(UTC) + MODEL_RETRY_IN)
        )
        async with self._engine.begin() as conn:
            await self._delay(conn, job, work, status, until)
            await JobRepository(conn).complete(job)
        logger.info("chapter job %s makes no call: %s", job.id, reason)

    async def _fail(self, job: Job, work: _Work, error: str, final: bool) -> None:
        async with self._engine.begin() as conn:
            if not await JobRepository(conn).fail(
                job, error, final, timedelta(seconds=self._settings.chapter_retry_delay_s)
            ):
                logger.warning("chapter job %s lost its lease before failing", job.id)
                return
            if final:
                due = datetime.now(UTC) + MODEL_RETRY_IN
                await self._delay(conn, job, work, "delayed_model", due)

    @staticmethod
    async def _delay(conn, job: Job, work: _Work, status: ChapterStatus, until: datetime) -> None:
        """Mark the chapter delayed and open the template quest, in the caller's transaction."""
        adventures = AdventureRepository(conn)
        await adventures.delay_chapter(work.chapter.id, job.id, status, until)
        await open_fallback_quest(
            adventures,
            job.family_id,
            work.quest.member_id,
            job.payload["locale"],
        )

    async def _store(self, job: Job, work: _Work, out, actual: int) -> None:
        """One transaction: chapter ready, next quest from the same answer, cost settled."""
        draft = QuestDraft(
            out.next_quest.title,
            out.next_quest.description,
            out.next_quest.skill,
            "model",
            out.next_quest.reaction,
            out.next_quest.kind,
        )
        if out.milestone is None and beat_of(work.chapter.seq) == "milestone":
            logger.warning("chapter job %s has no milestone after the retry", job.id)
        async with self._engine.begin() as conn:
            adventures = AdventureRepository(conn)
            await self._gate.settle(conn, job.id, job.attempts, actual)
            if await adventures.save_chapter(
                work.chapter.id,
                job.id,
                ChapterText(out.title, out.body, out.summary, out.milestone),
            ):
                await adventures.open_quest(job.family_id, work.quest.member_id, draft)
                if self._cover_on and out.milestone:
                    await self._order_growth_cover(conn, job, work, out.summary)
                if self._notify:  # the reminder worker sends it after this commit
                    ready_at = datetime.now(UTC).isoformat()
                    await JobRepository(conn).enqueue(
                        "notify", job.family_id, {"ready_at": ready_at}
                    )
            else:
                logger.info("chapter job %s was superseded: result dropped", job.id)
            if not await JobRepository(conn).complete(job):
                logger.warning("chapter job %s lost its lease before completing", job.id)

    @staticmethod
    async def _order_growth_cover(
        conn: AsyncConnection, job: Job, work: _Work, summary: str
    ) -> None:
        """On every 2nd milestone queue a new cover, in the transaction that stored the chapter.

        The image caps decide at the image worker: over the cap the old cover simply stays.
        """
        number = growth_cover_milestone(work.chapter.seq)
        stored = await WorldRepository(conn).get(job.family_id)
        if number is None or stored is None or stored.world is None or stored.status != "ready":
            return
        if not stored.world.cover_image_prompt:
            return
        world_job = await WorldRepository(conn).current_job_id(job.family_id)
        members = await FamilyRepository(conn).list_members(job.family_id)
        banned = [m.display_name for m in members] + [i for m in members for i in m.interests]
        banned += [m.age_band.value for m in members]
        banned += description_names(stored.custom_genre or "")
        story = GrowthStory(
            stored.world.tone, summary, await AdventureRepository(conn).milestones(job.family_id)
        )
        prompt = growth_cover_prompt(
            stored.world.cover_image_prompt,
            story,
            banned=banned,
            young_child=any(m.age_band is AgeBand.B3_5 for m in members),
        )
        if world_job and await ImageRepository(conn).create_pending(
            job.family_id, world_job, prompt, number
        ):
            payload = {"world_job_id": str(world_job), "milestone_no": number}
            await JobRepository(conn).enqueue("image", job.family_id, payload)

    async def run_forever(self) -> None:
        while True:
            try:
                if await self.run_once():
                    continue
            except Exception:  # the loop must outlive any one failed iteration
                logger.exception("chapter worker iteration failed")
            await asyncio.sleep(self._settings.world_poll_s)
