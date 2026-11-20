import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.chapter_writer import INSTRUCTIONS, ChapterSpec, ChapterWriter
from app.domain.adventure import NextQuest, QuestDraft, normalize_skill
from app.repositories.adventure_repository import AdventureRepository


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Замечать мелочи", "замечать мелочи"),
        ("  Наблюдательность ", "наблюдательность"),
        ("ИИ-помощник", "ИИ-помощник"),
        ("X", "x"),
        ("观察细节", "观察细节"),
        ("Écouter", "écouter"),
        ("уже строчное", "уже строчное"),
    ],
)
def test_skill_is_trimmed_and_starts_lowercase_unless_acronym(raw: str, stored: str) -> None:
    assert normalize_skill(raw) == stored


def test_a_whitespace_only_skill_is_rejected_so_the_output_retry_fires() -> None:
    quest = {"title": "t", "description": "d", "reaction": "r", "kind": "say", "skill": "   "}
    with pytest.raises(ValidationError):
        NextQuest.model_validate(quest)


def test_prompt_carries_previous_skills_and_the_rule_names_them() -> None:
    spec = ChapterSpec(
        "ru", "space", "w", None, "t", "d", None, ("adult",), 3, None, (), ("забота", "память")
    )
    assert '"previous_skills": ["забота", "память"]' in ChapterWriter.prompt(spec)
    assert "previous_skills" in INSTRUCTIONS


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def family(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    fid, mid = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO families (id, title) VALUES (:i, 't')"), {"i": fid})
        await conn.execute(
            text(
                "INSERT INTO members (id, family_id, display_name, age_band, role)"
                " VALUES (:i, :f, 'Ann', 'adult', 'adult')"
            ),
            {"i": mid, "f": fid},
        )
    return fid, mid


async def test_stored_skill_is_normalised_and_feeds_the_next_prompt(
    engine: AsyncEngine, family: tuple[uuid.UUID, uuid.UUID]
) -> None:
    fid, mid = family
    skills = ["Замечать мелочи", " Забота о месте", "замечать мелочи", "Память"]
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        last = None
        for skill in skills:
            last = await repo.open_quest(fid, mid, QuestDraft("t", "d", skill, "model"))
            assert last is not None
            await conn.execute(
                text("UPDATE quests SET status = 'done' WHERE id = :i"), {"i": last.id}
            )
        assert last is not None
        context = await repo.quest_context(last.id)
    assert context is not None
    assert context.recent_skills == ("память", "замечать мелочи", "забота о месте")


async def test_previous_skills_are_capped_to_the_most_recent(
    engine: AsyncEngine, family: tuple[uuid.UUID, uuid.UUID]
) -> None:
    fid, mid = family
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        last = None
        for n in range(12):
            last = await repo.open_quest(fid, mid, QuestDraft("t", "d", f"навык {n}", "model"))
            assert last is not None
            await conn.execute(
                text("UPDATE quests SET status = 'done' WHERE id = :i"), {"i": last.id}
            )
        assert last is not None
        context = await repo.quest_context(last.id)
    assert context is not None
    assert len(context.recent_skills) == 8
    assert context.recent_skills[0] == "навык 11"


async def test_skills_stored_before_normalisation_still_collapse(
    engine: AsyncEngine, family: tuple[uuid.UUID, uuid.UUID]
) -> None:
    fid, mid = family
    async with engine.begin() as conn:
        repo = AdventureRepository(conn)
        last = None
        for n in range(3):
            last = await repo.open_quest(fid, mid, QuestDraft("t", "d", f"s{n}", "model"))
            assert last is not None
            await conn.execute(
                text("UPDATE quests SET status = 'done' WHERE id = :i"), {"i": last.id}
            )
        await conn.execute(
            text("UPDATE quests SET skill = ' Память' WHERE seq = 1 AND family_id = :f"), {"f": fid}
        )
        await conn.execute(
            text("UPDATE quests SET skill = 'память ' WHERE seq = 3 AND family_id = :f"), {"f": fid}
        )
        assert last is not None
        context = await repo.quest_context(last.id)
    assert context is not None
    assert context.recent_skills == ("память ", "s1")


async def test_finished_quest_titles_are_the_family_s_own_capped_and_oldest_first(
    engine: AsyncEngine, family: tuple[uuid.UUID, uuid.UUID]
) -> None:
    fid, mid = family
    other = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, title) VALUES (:i, 'other')"),
            {"i": other},
        )
        repo = AdventureRepository(conn)
        last = None
        for n in range(12):
            last = await repo.open_quest(fid, mid, QuestDraft(f"квест {n}", "d", "s", "model"))
            assert last is not None
            await conn.execute(
                text("UPDATE quests SET status = 'done' WHERE id = :i"), {"i": last.id}
            )
        await conn.execute(
            text(
                "INSERT INTO quests (family_id, seq, title, description, skill, source, status)"
                " VALUES (:f, 1, 'чужой', 'd', 's', 'model', 'done')"
            ),
            {"f": other},
        )
        assert last is not None
        titles = await repo.finished_quest_titles(last.id)
    # The quest the chapter is written for is the latest entry: it is the likeliest to repeat.
    assert titles == tuple(f"квест {n}" for n in range(4, 12))
