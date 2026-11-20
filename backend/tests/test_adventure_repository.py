import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.domain.adventure import Quest, QuestDraft
from app.domain.errors import NotFound
from app.repositories.adventure_repository import AdventureRepository

QUEST = QuestDraft(
    "Find the lantern", "Look around the flat for a glow.", "observation", "template"
)
MODEL_QUEST = QuestDraft("Next", "Follow the story.", "focus", "model")


@dataclass(frozen=True)
class Ids:
    family: uuid.UUID
    member: uuid.UUID


async def opened(repo: AdventureRepository, ids: "Ids", draft: QuestDraft) -> Quest:
    quest = await repo.open_quest(ids.family, ids.member, draft)
    assert quest is not None
    return quest


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def ids(engine: AsyncEngine) -> Ids:
    family, member = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, title) VALUES (:id, 't')"), {"id": family}
        )
        await conn.execute(
            text(
                "INSERT INTO members (id, family_id, display_name, age_band, role)"
                " VALUES (:id, :f, 'Ann', 'adult', 'adult')"
            ),
            {"id": member, "f": family},
        )
    return Ids(family, member)


async def test_one_open_quest_per_family(engine: AsyncEngine, ids: Ids) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        first = await opened(repo, ids, QUEST)
        again = await opened(repo, ids, MODEL_QUEST)
    assert again.id == first.id and again.seq == 1
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO quests (family_id, seq, title, description, skill, source)"
                    " VALUES (:f, 2, 't', 'd', 's', 'template')"
                ),
                {"f": ids.family},
            )


async def test_next_quest_after_done_takes_next_seq(engine: AsyncEngine, ids: Ids) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        first = await opened(repo, ids, QUEST)
        await repo.mark_done(first.id, ids.family, ids.member, None, None)
        second = await opened(repo, ids, MODEL_QUEST)
    assert (second.seq, second.source, second.status) == (2, "model", "open")


async def test_repeated_done_mark_creates_one_event(
    engine: AsyncEngine, ids: Ids, db_fetch
) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        quest = await opened(repo, ids, QUEST)
        first, created1 = await repo.mark_done(quest.id, ids.family, ids.member, "hi", None)
        second, created2 = await repo.mark_done(quest.id, ids.family, ids.member, "bye", None)
    assert (created1, created2) == (True, False)
    assert second.id == first.id and second.note == "hi"
    rows = await db_fetch("SELECT status FROM quests WHERE id = $1", quest.id)
    assert [r["status"] for r in rows] == ["done"]
    assert len(await db_fetch("SELECT 1 FROM quest_events WHERE quest_id = $1", quest.id)) == 1


async def test_same_idem_key_returns_same_event(engine: AsyncEngine, ids: Ids) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        quest = await opened(repo, ids, QUEST)
        first, _ = await repo.mark_done(quest.id, ids.family, ids.member, None, "key-1")
        replay, created = await repo.mark_done(quest.id, ids.family, ids.member, None, "key-1")
        nxt = await opened(repo, ids, QUEST)
        other, other_created = await repo.mark_done(nxt.id, ids.family, ids.member, None, "key-1")
    assert replay.id == first.id and not created
    assert not other_created and other.quest_id == quest.id != nxt.id


async def test_second_chapter_for_quest_is_not_created(engine: AsyncEngine, ids: Ids) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        quest = await opened(repo, ids, QUEST)
        job1, job2 = uuid.uuid4(), uuid.uuid4()
        first, created1 = await repo.create_chapter(quest.id, job1)
        second, created2 = await repo.create_chapter(quest.id, job2)
    assert (created1, created2) == (True, False)
    assert second.id == first.id and second.status == "queued" and second.seq == quest.seq
    assert second.job_id == job1


async def test_adventure_returns_chapters_in_order_and_open_quest(
    engine: AsyncEngine, ids: Ids
) -> None:
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        assert (await repo.get_adventure(ids.family)).quest is None
        for _ in range(2):
            quest = await opened(repo, ids, QUEST)
            await repo.mark_done(quest.id, ids.family, ids.member, None, None)
            await repo.create_chapter(quest.id, uuid.uuid4())
        open_quest = await opened(repo, ids, QUEST)
        adventure = await repo.get_adventure(ids.family)
    assert [c.seq for c in adventure.chapters] == [1, 2]
    assert adventure.quest is not None and adventure.quest.id == open_quest.id


async def test_chapter_status_update_is_guarded_by_job(engine: AsyncEngine, ids: Ids) -> None:
    job = uuid.uuid4()
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        quest = await opened(repo, ids, QUEST)
        chapter, _ = await repo.create_chapter(quest.id, job)
        assert not await repo.update_chapter_status(chapter.id, uuid.uuid4(), "writing")
        assert await repo.update_chapter_status(chapter.id, job, "delayed_budget")
        adventure = await repo.get_adventure(ids.family)
    assert adventure.chapters[0].status == "delayed_budget"
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE chapters SET status = 'bogus' WHERE id = :id"), {"id": chapter.id}
            )


async def test_spend_row_is_unique_per_job_attempt(engine: AsyncEngine, ids: Ids) -> None:
    insert = text(
        "INSERT INTO llm_spend (family_id, job_id, attempt, reserved_micro_usd, state)"
        " VALUES (:f, :j, 1, 100, 'reserved')"
    )
    job = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(insert, {"f": ids.family, "j": job})
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(insert, {"f": ids.family, "j": job})


async def test_event_note_is_capped(engine: AsyncEngine, ids: Ids) -> None:
    async with engine.begin() as conn:
        quest = await opened(AdventureRepository(conn), ids, QUEST)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await AdventureRepository(conn).mark_done(
                quest.id, ids.family, ids.member, "x" * 281, None
            )


async def test_done_mark_for_another_familys_quest_is_rejected(
    engine: AsyncEngine, ids: Ids, db_fetch
) -> None:
    other = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, title) VALUES (:id, 't')"), {"id": other}
        )
        quest = await AdventureRepository(conn).open_quest(other, None, QUEST)
    assert quest is not None
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await AdventureRepository(conn).mark_done(quest.id, ids.family, ids.member, None, None)
    rows = await db_fetch("SELECT status FROM quests WHERE id = $1", quest.id)
    assert [r["status"] for r in rows] == ["open"]


async def test_chapter_for_unknown_quest_is_not_found(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        with pytest.raises(NotFound):
            await AdventureRepository(conn).create_chapter(uuid.uuid4(), uuid.uuid4())


async def test_family_delete_keeps_spend_rows(engine: AsyncEngine, ids: Ids, db_fetch) -> None:
    job = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO llm_spend (family_id, job_id, attempt, reserved_micro_usd)"
                " VALUES (:f, :j, 1, 100)"
            ),
            {"f": ids.family, "j": job},
        )
        await conn.execute(text("DELETE FROM families WHERE id = :f"), {"f": ids.family})
    rows = await db_fetch(
        "SELECT family_id, reserved_micro_usd FROM llm_spend WHERE job_id = $1", job
    )
    assert [(r["family_id"], r["reserved_micro_usd"]) for r in rows] == [(None, 100)]


class ClosingConn:
    """Connection proxy: right after the quest INSERT, the family's quests are marked done.

    It runs on the same connection, standing in for a concurrent transaction that closed the
    open quest between the INSERT and the read; other families' rows are left alone.
    """

    def __init__(self, conn: AsyncConnection, family_id: uuid.UUID) -> None:
        self._conn = conn
        self._family_id = family_id

    async def execute(self, statement, params=None):
        result = await self._conn.execute(statement, params)
        if "INSERT INTO quests" in str(statement):
            await self._conn.execute(
                text("UPDATE quests SET status = 'done' WHERE family_id = :f"),
                {"f": self._family_id},
            )
        return result


async def test_open_quest_returns_none_when_the_open_one_closes_mid_call(
    engine: AsyncEngine, ids: Ids
) -> None:
    async with engine.begin() as conn:
        await opened(AdventureRepository(conn), ids, QUEST)
        proxy = cast(AsyncConnection, ClosingConn(conn, ids.family))
        assert await AdventureRepository(proxy).open_quest(ids.family, ids.member, QUEST) is None


async def test_family_delete_clears_spend_chapter_id_and_keeps_totals(
    engine: AsyncEngine, ids: Ids, db_fetch
) -> None:
    job = uuid.uuid4()
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        quest = await opened(repo, ids, QUEST)
        chapter, _ = await repo.create_chapter(quest.id, job)
        await conn.execute(
            text(
                "INSERT INTO llm_spend (family_id, chapter_id, job_id, attempt, reserved_micro_usd)"
                " VALUES (:f, :c, :j, 1, 100)"
            ),
            {"f": ids.family, "c": chapter.id, "j": job},
        )
        await conn.execute(text("DELETE FROM families WHERE id = :f"), {"f": ids.family})
    rows = await db_fetch(
        "SELECT chapter_id, family_id, reserved_micro_usd FROM llm_spend WHERE job_id = $1", job
    )
    assert [(r["chapter_id"], r["family_id"], r["reserved_micro_usd"]) for r in rows] == [
        (None, None, 100)
    ]


async def test_skills_are_one_per_spelling_in_first_seen_form(
    engine: AsyncEngine, ids: Ids
) -> None:
    async with engine.begin() as conn:
        for seq, skill in enumerate(["care", "Care", "care ", "find"], start=1):
            await conn.execute(
                text(
                    "INSERT INTO quests (family_id, seq, title, description, skill, source, status)"
                    " VALUES (:f, :s, 't', 'd', :k, 'template', 'done')"
                ),
                {"f": ids.family, "s": seq, "k": skill},
            )
        got = await AdventureRepository(conn).get_adventure(ids.family)
    assert got.skills == ["care", "find"]
