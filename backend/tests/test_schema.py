import asyncpg


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
