from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.money_gate import MoneyGate
from app.core.config import Settings
from tests.test_world_api import adult_with_child

IMAGE_RESERVE = 45_000  # 0.045 USD


@pytest.fixture
async def engine(postgres_url: str, db_fetch) -> AsyncIterator[AsyncEngine]:
    await db_fetch("DELETE FROM llm_spend")
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def gate(engine: AsyncEngine, postgres_url: str) -> MoneyGate:
    return MoneyGate(engine, Settings(_env_file=None, database_url=postgres_url))


async def new_family(client: AsyncClient) -> UUID:
    _, _, fid, *_ = await adult_with_child(client)
    return UUID(fid)


def test_image_cap_defaults(postgres_url: str) -> None:
    s = Settings(_env_file=None, database_url=postgres_url)
    assert (s.image_family_daily_cap_usd, s.image_global_daily_cap_usd) == (0.15, 1.0)


async def test_image_reservation_leaves_the_text_allowance(
    client: AsyncClient, gate: MoneyGate
) -> None:
    fid = await new_family(client)
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve(fid, uuid4(), 1, 50_000) == "reserved"  # full text cap still free


async def test_text_reservation_leaves_the_image_allowance(
    client: AsyncClient, gate: MoneyGate
) -> None:
    fid = await new_family(client)
    assert await gate.reserve(fid, uuid4(), 1, 50_000) == "reserved"
    assert await gate.reserve(fid, uuid4(), 1, 1) == "over_cap"
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"


async def test_family_image_cap_rejects_the_fourth_image(
    client: AsyncClient, gate: MoneyGate, db_fetch
) -> None:
    fid = await new_family(client)
    got = [await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) for _ in range(4)]
    assert got == ["reserved", "reserved", "reserved", "over_cap"]
    assert len(await db_fetch("SELECT 1 FROM llm_spend WHERE kind = 'image'")) == 3


async def test_global_image_cap_rejects(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str
) -> None:
    gate = MoneyGate(
        engine,
        Settings(
            _env_file=None,
            database_url=postgres_url,
            image_family_daily_cap_usd=1.0,
            image_global_daily_cap_usd=0.09,
        ),
    )
    first, second = await new_family(client), await new_family(client)
    assert await gate.reserve_image(first, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_image(second, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_image(second, uuid4(), 1, IMAGE_RESERVE) == "over_cap"


async def test_image_repeat_of_job_attempt_stays_a_repeat(
    client: AsyncClient, gate: MoneyGate, db_fetch
) -> None:
    fid, job = await new_family(client), uuid4()
    assert await gate.reserve_image(fid, job, 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_image(fid, job, 1, IMAGE_RESERVE) == "duplicate"
    assert len(await db_fetch("SELECT 1 FROM llm_spend WHERE job_id = $1", job)) == 1


async def test_existing_callers_default_to_text(
    client: AsyncClient, gate: MoneyGate, db_fetch
) -> None:
    fid, job = await new_family(client), uuid4()
    await gate.reserve(fid, job, 1, 10)
    (row,) = await db_fetch("SELECT kind FROM llm_spend WHERE job_id = $1", job)
    assert row["kind"] == "text"


WORLD3D_RESERVE = 180_000  # 0.18 USD


def test_world3d_cap_defaults_and_model_off(postgres_url: str) -> None:
    s = Settings(_env_file=None, database_url=postgres_url)
    assert (s.world3d_family_daily_cap_usd, s.world3d_global_daily_cap_usd) == (0.20, 3.0)
    assert s.world3d_model == ""


async def test_world3d_reservation_leaves_text_and_image_allowance(
    client: AsyncClient, gate: MoneyGate
) -> None:
    fid = await new_family(client)
    assert await gate.reserve_world3d(fid, uuid4(), 1, WORLD3D_RESERVE) == "reserved"
    assert await gate.reserve(fid, uuid4(), 1, 50_000) == "reserved"
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"


async def test_text_and_image_reservations_leave_the_world3d_allowance(
    client: AsyncClient, gate: MoneyGate
) -> None:
    fid = await new_family(client)
    assert await gate.reserve(fid, uuid4(), 1, 50_000) == "reserved"
    assert await gate.reserve_image(fid, uuid4(), 1, IMAGE_RESERVE) == "reserved"
    assert await gate.reserve_world3d(fid, uuid4(), 1, WORLD3D_RESERVE) == "reserved"


async def test_family_cap_rejects_the_second_world_of_a_day(
    client: AsyncClient, gate: MoneyGate, db_fetch
) -> None:
    fid = await new_family(client)
    got = [await gate.reserve_world3d(fid, uuid4(), 1, WORLD3D_RESERVE) for _ in range(2)]
    assert got == ["reserved", "over_cap"]
    assert len(await db_fetch("SELECT 1 FROM llm_spend WHERE kind = 'world3d'")) == 1


async def test_global_world3d_cap_rejects(
    client: AsyncClient, engine: AsyncEngine, postgres_url: str
) -> None:
    gate = MoneyGate(
        engine,
        Settings(
            _env_file=None,
            database_url=postgres_url,
            world3d_family_daily_cap_usd=1.0,
            world3d_global_daily_cap_usd=0.30,
        ),
    )
    first, second = await new_family(client), await new_family(client)
    assert await gate.reserve_world3d(first, uuid4(), 1, WORLD3D_RESERVE) == "reserved"
    assert await gate.reserve_world3d(second, uuid4(), 1, WORLD3D_RESERVE) == "over_cap"
