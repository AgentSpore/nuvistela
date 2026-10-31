import asyncpg
import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.spend import PostgresSpendStore

from app.agent.errors import AgentBudgetExceededError
from app.agent.factory import build_game_master
from app.agent.runtime import GameMasterRuntime
from tests.agent.conftest import MemoryConversations


@pytest.fixture
async def pool(postgres_url: str):
    p = await asyncpg.create_pool(postgres_url.replace("+asyncpg", ""), min_size=1, max_size=2)
    yield p
    await p.close()


async def test_v2_migration_creates_the_harness_tables(db_fetch) -> None:
    rows = await db_fetch("SELECT to_regclass('spend_counters') AS c, to_regclass('spend_dedup') AS d")
    assert rows[0]["c"] and rows[0]["d"]


async def test_daily_budget_is_shared_between_two_workers(
    pool, make_settings, deps_factory, event
) -> None:
    settings = make_settings(agent_family_daily_tokens=1)

    def worker() -> GameMasterRuntime:  # separate store instance = separate process
        agent = build_game_master(settings, spend_store=PostgresSpendStore(pool))
        return GameMasterRuntime(agent, deps_factory, settings, MemoryConversations())

    one, two = worker(), worker()
    with one.agent.override(model=TestModel()), two.agent.override(model=TestModel()):
        await one.run_turn(event)
        with pytest.raises(AgentBudgetExceededError):
            await two.run_turn(event)
