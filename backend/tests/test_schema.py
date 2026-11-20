import asyncpg
import pytest


async def test_members_has_no_redundant_family_index(postgres_url: str) -> None:
    """UNIQUE (family_id, tg_user_id) already serves family_id lookups."""
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        names = await conn.fetchval(
            "SELECT array_agg(indexname) FROM pg_indexes WHERE tablename = 'members'"
        )
    finally:
        await conn.close()
    assert "members_family_id_idx" not in names
    assert "members_family_id_tg_user_id_key" in names


async def test_agent_messages_has_no_created_at_index(postgres_url: str) -> None:
    """History is read by (family_id, seq); a created_at index would only add write cost."""
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        names = await conn.fetchval(
            "SELECT array_agg(indexname) FROM pg_indexes WHERE tablename = 'agent_messages'"
        )
    finally:
        await conn.close()
    assert "agent_messages_family_created_idx" not in names
    assert "agent_messages_family_seq_idx" in names


async def test_chapters_has_the_partial_requeue_index(postgres_url: str) -> None:
    """requeue_due runs before every claim; the index covers only delayed chapters."""
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        ddl = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'chapters_requeue_idx'"
        )
    finally:
        await conn.close()
    assert ddl is not None and "next_run_at" in ddl and "delayed_budget" in ddl


async def test_custom_genre_check_allows_300_and_rejects_301(postgres_url: str) -> None:
    """V17 widened the own-world description from 60 to 300 characters."""
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        fids = [
            await conn.fetchval("INSERT INTO families (title) VALUES ('t') RETURNING id")
            for _ in range(2)
        ]
        insert = (
            "INSERT INTO worlds (family_id, status, genre, custom_genre, job_id)"
            " VALUES ($1, 'pending', 'custom', $2, gen_random_uuid())"
        )
        await conn.execute(insert, fids[0], "в" * 300)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(insert, fids[1], "в" * 301)
    finally:
        await conn.close()


async def test_v18_families_locale_check_allows_the_four_app_locales(postgres_url: str) -> None:
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        for locale in ("ru", "en", "es", "zh-CN"):
            await conn.execute("INSERT INTO families (title, locale) VALUES ('t', $1)", locale)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("INSERT INTO families (title, locale) VALUES ('t', 'fr')")
        defs = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint"
            " WHERE conrelid = 'families'::regclass AND contype = 'c'"
        )
    finally:
        await conn.close()
    assert sum("locale" in r["d"] for r in defs) == 1


async def test_v19_quest_reaction_is_nullable_and_capped_at_280(postgres_url: str) -> None:
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        fids = [
            await conn.fetchval("INSERT INTO families (title) VALUES ('t') RETURNING id")
            for _ in range(3)
        ]
        insert = (
            "INSERT INTO quests (family_id, seq, title, description, skill, source, reaction)"
            " VALUES ($1, $2, 't', 'd', 's', 'model', $3)"
        )
        await conn.execute(insert, fids[0], 1, None)
        await conn.execute(insert, fids[1], 1, "в" * 280)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(insert, fids[2], 1, "в" * 281)
    finally:
        await conn.close()
