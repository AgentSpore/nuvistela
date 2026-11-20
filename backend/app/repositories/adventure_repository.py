from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.adventure import (
    RECENT_KINDS,
    RECENT_SKILLS,
    Adventure,
    Chapter,
    ChapterStatus,
    ChapterText,
    Quest,
    QuestContext,
    QuestDraft,
    QuestEvent,
    normalize_skill,
)
from app.domain.errors import NotFound

POLL_WRITE_EVERY = timedelta(seconds=5)
_QUEST_COLS = (
    "id, family_id, member_id, seq, title, description, skill, source, status, reaction, kind"
)
_EVENT_COLS = "id, quest_id, member_id, note, idem_key"
_CHAPTER_COLS = "id, quest_id, seq, status, title, body, summary, job_id, next_run_at, milestone"


def _quest(row: Row) -> Quest:
    return Quest(*row)


def _event(row: Row) -> QuestEvent:
    return QuestEvent(*row)


def _chapter(row: Row) -> Chapter:
    return Chapter(*row)


RECENT_QUEST_TITLES = 8  # finished quest titles the chapter prompt lists to avoid repeats


class AdventureRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def touch_poll(self, family_id: UUID, every: timedelta = POLL_WRITE_EVERY) -> None:
        """Note that a client polled the adventure; written at most once per `every`."""
        await self._conn.execute(
            text(
                "UPDATE families SET last_adventure_poll_at = now() WHERE id = :fid"
                " AND (last_adventure_poll_at IS NULL"
                " OR last_adventure_poll_at < now() - CAST(:every AS interval))"
            ),
            {"fid": family_id, "every": every},
        )

    async def next_quest_seq(self, family_id: UUID) -> int:
        """The number `open_quest` gives the family's next quest."""
        return (
            await self._conn.execute(
                text("SELECT coalesce(max(seq), 0) + 1 FROM quests WHERE family_id = :fid"),
                {"fid": family_id},
            )
        ).scalar_one()

    async def open_quest(
        self,
        family_id: UUID,
        member_id: UUID | None,
        draft: QuestDraft,
    ) -> Quest | None:
        """Create the family's next quest, or return the open one: a family has at most one.

        None when the open quest was marked done between the skipped insert and the read.
        """
        await self._conn.execute(
            text(
                "INSERT INTO quests"
                " (family_id, member_id, seq, title, description, skill, source, reaction, kind)"
                " SELECT :fid, :mid, coalesce(max(seq), 0) + 1, :title, :descr, :skill, :source,"
                " :reaction, :kind"
                " FROM quests WHERE family_id = :fid"
                " ON CONFLICT DO NOTHING"
            ),
            {
                "fid": family_id,
                "mid": member_id,
                "title": draft.title,
                "descr": draft.description,
                "skill": normalize_skill(draft.skill),
                "source": draft.source,
                "reaction": draft.reaction,
                "kind": draft.kind,
            },
        )
        row = (
            await self._conn.execute(
                text(
                    f"SELECT {_QUEST_COLS} FROM quests WHERE family_id = :fid AND status = 'open'"
                ),
                {"fid": family_id},
            )
        ).one_or_none()
        return None if row is None else _quest(row)

    async def open_first_quest(
        self, family_id: UUID, member_id: UUID | None, draft: QuestDraft
    ) -> bool:
        """Create quest 1 unless the family already has any quest; True when this call did.

        Safe under worker retries and concurrent writers: a second insert hits the
        (family_id, seq) key and writes nothing.
        """
        result = await self._conn.execute(
            text(
                "INSERT INTO quests"
                " (family_id, member_id, seq, title, description, skill, source, reaction, kind)"
                " SELECT :fid, :mid, 1, :title, :descr, :skill, :source, :reaction, :kind"
                " WHERE NOT EXISTS (SELECT 1 FROM quests WHERE family_id = :fid)"
                " ON CONFLICT DO NOTHING"
            ),
            {
                "fid": family_id,
                "mid": member_id,
                "title": draft.title,
                "descr": draft.description,
                "skill": normalize_skill(draft.skill),
                "source": draft.source,
                "reaction": draft.reaction,
                "kind": draft.kind,
            },
        )
        return result.rowcount == 1

    async def mark_done(
        self,
        quest_id: UUID,
        family_id: UUID,
        member_id: UUID | None,
        note: str | None,
        idem_key: str | None,
    ) -> tuple[QuestEvent, bool]:
        """Record the quest as done; the bool is True only for the call that created the event.

        A repeat returns the stored event. When `idem_key` already belongs to another quest,
        that quest's event comes back and its `quest_id` differs from the one asked for.
        """
        inserted = (
            await self._conn.execute(
                text(
                    "INSERT INTO quest_events"
                    " (quest_id, family_id, member_id, kind, note, idem_key)"
                    " VALUES (:qid, :fid, :mid, 'done', :note, :key)"
                    " ON CONFLICT DO NOTHING"
                    f" RETURNING {_EVENT_COLS}"
                ),
                {
                    "qid": quest_id,
                    "fid": family_id,
                    "mid": member_id,
                    "note": note,
                    "key": idem_key,
                },
            )
        ).first()
        if inserted is not None:
            await self._conn.execute(
                text("UPDATE quests SET status = 'done' WHERE id = :qid"), {"qid": quest_id}
            )
            return _event(inserted), True
        existing = (
            await self._conn.execute(
                text(
                    f"SELECT {_EVENT_COLS} FROM quest_events WHERE family_id = :fid"
                    " AND (quest_id = :qid OR idem_key = :key)"
                    " ORDER BY (quest_id = :qid) DESC LIMIT 1"
                ),
                {"qid": quest_id, "fid": family_id, "key": idem_key},
            )
        ).one()
        return _event(existing), False

    async def create_chapter(self, quest_id: UUID, job_id: UUID) -> tuple[Chapter, bool]:
        """Queue the quest's chapter; the bool is False when it already existed (job_id unused).

        Raises NotFound for an unknown quest.
        """
        created = (
            await self._conn.execute(
                text(
                    "INSERT INTO chapters (family_id, quest_id, seq, job_id)"
                    " SELECT family_id, id, seq, :job FROM quests WHERE id = :qid"
                    " ON CONFLICT (quest_id) DO NOTHING"
                    f" RETURNING {_CHAPTER_COLS}"
                ),
                {"qid": quest_id, "job": job_id},
            )
        ).first()
        if created is not None:
            return _chapter(created), True
        row = (
            await self._conn.execute(
                text(f"SELECT {_CHAPTER_COLS} FROM chapters WHERE quest_id = :qid"),
                {"qid": quest_id},
            )
        ).first()
        if row is None:
            raise NotFound("quest not found")
        return _chapter(row), False

    async def get_adventure(self, family_id: UUID) -> Adventure:
        """The family's chapters in story order plus its open quest, if any."""
        chapters = await self._conn.execute(
            text(f"SELECT {_CHAPTER_COLS} FROM chapters WHERE family_id = :fid ORDER BY seq"),
            {"fid": family_id},
        )
        quest = (
            await self._conn.execute(
                text(
                    f"SELECT {_QUEST_COLS} FROM quests WHERE family_id = :fid AND status = 'open'"
                ),
                {"fid": family_id},
            )
        ).first()
        skills = await self._conn.execute(
            text(
                "SELECT (array_agg(skill ORDER BY seq))[1] FROM quests"
                " WHERE family_id = :fid AND status = 'done'"
                " GROUP BY lower(btrim(skill)) ORDER BY min(seq)"
            ),
            {"fid": family_id},
        )
        return Adventure(
            None if quest is None else _quest(quest),
            [_chapter(r) for r in chapters],
            [r[0] for r in skills],
        )

    async def update_chapter_status(
        self, chapter_id: UUID, job_id: UUID, status: ChapterStatus
    ) -> bool:
        """Set the status; False (nothing written) when `job_id` is not the chapter's job."""
        result = await self._conn.execute(
            text("UPDATE chapters SET status = :status WHERE id = :id AND job_id = :job"),
            {"id": chapter_id, "job": job_id, "status": status},
        )
        return result.rowcount == 1

    async def lock_quest(self, quest_id: UUID, family_id: UUID) -> Quest | None:
        """Row-lock the family's quest until the transaction ends; None if not theirs."""
        row = (
            await self._conn.execute(
                text(
                    f"SELECT {_QUEST_COLS} FROM quests WHERE id = :id AND family_id = :fid"
                    " FOR UPDATE"
                ),
                {"id": quest_id, "fid": family_id},
            )
        ).first()
        return None if row is None else _quest(row)

    async def get_chapter(self, chapter_id: UUID, family_id: UUID) -> Chapter | None:
        """The family's chapter by id; None if it does not exist or is another family's."""
        row = (
            await self._conn.execute(
                text(f"SELECT {_CHAPTER_COLS} FROM chapters WHERE id = :id AND family_id = :fid"),
                {"id": chapter_id, "fid": family_id},
            )
        ).first()
        return None if row is None else _chapter(row)

    async def chapter_of_quest(self, quest_id: UUID) -> Chapter | None:
        """The chapter written for a quest, None before its done mark."""
        row = (
            await self._conn.execute(
                text(f"SELECT {_CHAPTER_COLS} FROM chapters WHERE quest_id = :qid"),
                {"qid": quest_id},
            )
        ).first()
        return None if row is None else _chapter(row)

    async def count_recent_retries(self, family_id: UUID, window: timedelta) -> int:
        """Chapter jobs the family queued by retrying, not the first write of each chapter."""
        row = await self._conn.execute(
            text(
                "SELECT count(*) FROM jobs WHERE kind = 'chapter' AND family_id = :fid"
                " AND payload ? 'retry' AND created_at > now() - CAST(:window AS interval)"
            ),
            {"fid": family_id, "window": window},
        )
        return row.scalar_one()

    async def requeue_chapter(self, chapter_id: UUID, job_id: UUID) -> bool:
        """Hand a delayed chapter to a new job; False when it is not delayed (nothing written)."""
        result = await self._conn.execute(
            text(
                "UPDATE chapters SET status = 'queued', job_id = :job, next_run_at = NULL"
                " WHERE id = :id AND status IN ('delayed_model', 'delayed_budget')"
            ),
            {"id": chapter_id, "job": job_id},
        )
        return result.rowcount == 1

    async def quest_context(self, quest_id: UUID) -> QuestContext | None:
        """The done quest, its note, the latest earlier chapter summary, the members' age bands."""
        row = (
            await self._conn.execute(
                text(
                    "SELECT q.title, q.description, q.member_id, e.note, q.reaction, ("
                    "   SELECT c.summary FROM chapters c WHERE c.family_id = q.family_id"
                    "   AND c.seq < q.seq AND c.status = 'ready' ORDER BY c.seq DESC LIMIT 1),"
                    " (SELECT array_agg(m.age_band ORDER BY m.created_at, m.id) FROM members m"
                    "  WHERE m.family_id = q.family_id),"
                    " (SELECT coalesce(array_agg(r.kind ORDER BY r.seq), '{}') FROM ("
                    "   SELECT kind, seq FROM quests WHERE family_id = q.family_id"
                    "   AND seq <= q.seq ORDER BY seq DESC LIMIT :recent) r"
                    "  WHERE r.kind IS NOT NULL),"
                    " (SELECT coalesce(array_agg(s.skill ORDER BY s.last DESC), '{}') FROM ("
                    "   SELECT (array_agg(skill ORDER BY seq DESC))[1] AS skill, max(seq) AS last"
                    "   FROM quests WHERE family_id = q.family_id AND seq <= q.seq"
                    "   GROUP BY lower(btrim(skill)) ORDER BY last DESC LIMIT :skills) s)"
                    " FROM quests q LEFT JOIN quest_events e"
                    " ON e.quest_id = q.id AND e.kind = 'done'"
                    " WHERE q.id = :qid"
                ),
                {"qid": quest_id, "recent": RECENT_KINDS, "skills": RECENT_SKILLS},
            )
        ).first()
        if row is None:
            return None
        *head, bands, kinds, skills = row
        return QuestContext(*head, tuple(bands or ()), tuple(kinds), tuple(skills))

    async def finished_quest_titles(self, quest_id: UUID) -> tuple[str, ...]:
        """Titles of the family's done quests up to this one: the latest few, oldest first."""
        rows = await self._conn.execute(
            text(
                "SELECT t.title FROM (SELECT p.title, p.seq FROM quests q JOIN quests p"
                " ON p.family_id = q.family_id AND p.seq <= q.seq AND p.status = 'done'"
                " WHERE q.id = :qid ORDER BY p.seq DESC LIMIT :n) t ORDER BY t.seq"
            ),
            {"qid": quest_id, "n": RECENT_QUEST_TITLES},
        )
        return tuple(r[0] for r in rows)

    async def milestones(self, family_id: UUID) -> list[str]:
        """The milestone lines of the family's ready chapters in story order, written since the
        current world became ready: the story goes on across a regeneration, the world does not."""
        rows = await self._conn.execute(
            text(
                "SELECT c.milestone FROM chapters c JOIN worlds w ON w.family_id = c.family_id"
                " WHERE c.family_id = :fid AND c.status = 'ready' AND c.milestone IS NOT NULL"
                " AND c.created_at >= w.updated_at ORDER BY c.seq"
            ),
            {"fid": family_id},
        )
        return [r[0] for r in rows]

    async def save_chapter(self, chapter_id: UUID, job_id: UUID, written: ChapterText) -> bool:
        """Store the written chapter as ready; False when `job_id` no longer owns the chapter."""
        result = await self._conn.execute(
            text(
                "UPDATE chapters SET status = 'ready', title = :title, body = :body,"
                " summary = :summary, milestone = :milestone, next_run_at = NULL"
                " WHERE id = :id AND job_id = :job"
            ),
            {"id": chapter_id, "job": job_id, **asdict(written)},
        )
        return result.rowcount == 1

    async def delay_chapter(
        self, chapter_id: UUID, job_id: UUID, status: ChapterStatus, until: datetime
    ) -> bool:
        """Set a delayed status and when it is due again; False if not the job's chapter."""
        result = await self._conn.execute(
            text(
                "UPDATE chapters SET status = :status, next_run_at = :until"
                " WHERE id = :id AND job_id = :job"
            ),
            {"id": chapter_id, "job": job_id, "status": status, "until": until},
        )
        return result.rowcount == 1

    async def requeue_due(self, max_auto_jobs: int) -> int:
        """Give every delayed chapter whose time has come a new job; returns how many.

        A chapter that already had `max_auto_jobs` automatic jobs stays for the retry button.
        Rows are locked with SKIP LOCKED and the status flips in the same statement, so two
        workers never queue the same chapter twice.
        """
        result = await self._conn.execute(
            text(
                "WITH due AS (SELECT c.id, c.family_id, c.quest_id FROM chapters c"
                "  WHERE c.status IN ('delayed_model', 'delayed_budget') AND c.next_run_at <= now()"
                "  AND (SELECT count(*) FROM jobs j WHERE j.kind = 'chapter' AND j.payload ? 'auto'"
                "       AND j.payload->>'quest_id' = c.quest_id::text) < :max_auto"
                "  FOR UPDATE OF c SKIP LOCKED),"
                " fresh AS (INSERT INTO jobs (kind, family_id, payload)"
                "  SELECT 'chapter', d.family_id, jsonb_build_object('quest_id', d.quest_id::text,"
                "   'locale', (SELECT locale FROM families WHERE id = d.family_id), 'auto', true)"
                "  FROM due d RETURNING id, payload->>'quest_id' AS quest_id)"
                " UPDATE chapters c SET status = 'queued', job_id = f.id, next_run_at = NULL"
                " FROM fresh f WHERE c.quest_id::text = f.quest_id"
            ),
            {"max_auto": max_auto_jobs},
        )
        return result.rowcount
