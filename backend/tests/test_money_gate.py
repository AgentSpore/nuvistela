import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.money_gate import MoneyGate
from app.core.config import Settings
from tests.test_world_api import adult_with_child


def settings(url: str, family_micro: int, global_micro: int) -> Settings:
    return Settings(
        _env_file=None,
        database_url=url,
        llm_family_daily_cap_usd=family_micro / 1_000_000,
        llm_global_daily_cap_usd=global_micro / 1_000_000,
    )


@pytest.fixture
async def engine(postgres_url: str, db_fetch) -> AsyncIterator[AsyncEngine]:
    await db_fetch("DELETE FROM llm_spend")
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


async def new_family(client: AsyncClient) -> UUID:
    _, _, fid, *_ = await adult_with_child(client)
    return UUID(fid)


async def test_cap_checked_before_call_leaves_no_reservation(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, db_fetch
) -> None:
    fid = await new_family(client)
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    assert await gate.reserve(fid, uuid4(), 1, 101) == "over_cap"
    assert await db_fetch("SELECT 1 FROM llm_spend WHERE family_id = $1", fid) == []


async def test_family_cap_counts_reserved_and_settled_money(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str
) -> None:
    fid, job = await new_family(client), uuid4()
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    assert await gate.reserve(fid, job, 1, 70) == "reserved"
    assert await gate.reserve(fid, uuid4(), 1, 40) == "over_cap"  # the reserve counts
    async with engine.begin() as conn:
        await gate.settle(conn, job, 1, 20)
    assert await gate.reserve(fid, uuid4(), 1, 40) == "reserved"  # the actual cost counts


async def test_settle_records_actual_cost(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, db_fetch
) -> None:
    fid, job = await new_family(client), uuid4()
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    await gate.reserve(fid, job, 1, 70)
    async with engine.begin() as conn:
        await gate.settle(conn, job, 1, 25)
    (row,) = await db_fetch("SELECT * FROM llm_spend WHERE job_id = $1", job)
    assert (row["reserved_micro_usd"], row["actual_micro_usd"], row["state"]) == (70, 25, "settled")


async def test_same_job_attempt_reserves_once(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, db_fetch
) -> None:
    fid, job = await new_family(client), uuid4()
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    assert await gate.reserve(fid, job, 1, 10) == "reserved"
    assert await gate.reserve(fid, job, 1, 10) == "duplicate"
    assert len(await db_fetch("SELECT 1 FROM llm_spend WHERE job_id = $1", job)) == 1


async def test_parallel_reservations_admit_exactly_what_fits_in_the_family_cap(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str
) -> None:
    fid = await new_family(client)
    gate = MoneyGate(engine, settings(postgres_url, 100, 100_000))
    got = await asyncio.gather(*(gate.reserve(fid, uuid4(), 1, 30) for _ in range(8)))
    assert got.count("reserved") == 3 and got.count("over_cap") == 5


async def test_parallel_reservations_never_exceed_the_global_cap(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, db_fetch
) -> None:
    fids = [await new_family(client) for _ in range(3)]
    gate = MoneyGate(engine, settings(postgres_url, 100_000, 100))
    got = await asyncio.gather(
        *(gate.reserve(fid, uuid4(), 1, 30) for fid in fids for _ in range(4))
    )
    assert got.count("reserved") == 3
    (total,) = await db_fetch("SELECT sum(reserved_micro_usd) AS s FROM llm_spend")
    assert total["s"] <= 100


async def test_yesterdays_spend_is_not_counted(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, db_fetch
) -> None:
    fid = await new_family(client)
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    await gate.reserve(fid, uuid4(), 1, 90)
    await db_fetch("UPDATE llm_spend SET created_at = now() - interval '25 hours'")
    assert await gate.reserve(fid, uuid4(), 1, 90) == "reserved"


async def test_settle_without_a_reservation_logs_a_warning(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str, caplog
) -> None:
    gate = MoneyGate(engine, settings(postgres_url, 100, 1000))
    async with engine.begin() as conn:
        assert await gate.settle(conn, uuid4(), 1, 5) is False
    assert "no reservation to settle" in caplog.text
