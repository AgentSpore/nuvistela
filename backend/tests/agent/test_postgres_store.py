from functools import cache

import asyncpg
import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.models import AgentEvent
from app.agent.postgres_store import PostgresConversationStore


@cache
def turn(n: int):
    return [
        ModelRequest(parts=[UserPromptPart(f"q{n}")]),
        ModelResponse(parts=[TextPart(f"a{n}")]),
    ]


@pytest.fixture
async def family_id(postgres_url: str):
    conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    ids = [await conn.fetchval("INSERT INTO families (title) VALUES ('t') RETURNING id")]
    ids.append(await conn.fetchval("INSERT INTO families (title) VALUES ('t2') RETURNING id"))
    await conn.close()
    return [str(i) for i in ids]


@pytest.fixture
async def engine(postgres_url: str):
    eng = create_async_engine(postgres_url)
    yield eng
    await eng.dispose()


def ev(family: str) -> AgentEvent:
    return AgentEvent(family_id=family, channel="web", kind="message", text="x", member_id=None)


async def test_empty_history_loads_empty(engine, family_id) -> None:
    async with engine.begin() as conn:
        assert await PostgresConversationStore(conn).load(family_id[0], 10) == []


async def test_roundtrip_keeps_order_and_types(engine, family_id) -> None:
    async with engine.begin() as conn:
        store = PostgresConversationStore(conn)
        await store.append(ev(family_id[0]), turn(1) + turn(2))
    async with engine.begin() as conn:
        got = await PostgresConversationStore(conn).load(family_id[0], 10)
    assert got == turn(1) + turn(2)


async def test_history_longer_than_limit_returns_newest_oldest_first(engine, family_id) -> None:
    async with engine.begin() as conn:
        store = PostgresConversationStore(conn)
        for n in range(5):
            await store.append(ev(family_id[0]), turn(n))
        got = await store.load(family_id[0], 3)
    assert got == turn(3)[1:] + turn(4)  # last 3 of 10 messages: a3, q4, a4


async def test_load_is_scoped_to_family(engine, family_id) -> None:
    async with engine.begin() as conn:
        store = PostgresConversationStore(conn)
        await store.append(ev(family_id[0]), turn(1))
        assert await store.load(family_id[1], 10) == []


async def test_append_rolls_back_with_the_request_transaction(engine, family_id) -> None:
    with pytest.raises(RuntimeError):
        async with engine.begin() as conn:
            await PostgresConversationStore(conn).append(ev(family_id[0]), turn(1))
            raise RuntimeError("request failed")
    async with engine.begin() as conn:
        assert await PostgresConversationStore(conn).load(family_id[0], 10) == []


async def test_rows_carry_role_channel_member(engine, family_id, db_fetch) -> None:
    async with engine.begin() as conn:
        await PostgresConversationStore(conn).append(ev(family_id[0]), turn(1))
    rows = await db_fetch(
        "SELECT role, channel, member_id FROM agent_messages WHERE family_id = $1::uuid"
        " ORDER BY created_at",
        family_id[0],
    )
    assert [(r["role"], r["channel"]) for r in rows] == [("user", "web"), ("agent", "web")]
