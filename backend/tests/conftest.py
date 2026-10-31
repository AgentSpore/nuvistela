import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent
from testcontainers.community.postgres import PostgresContainer

from app.agent.deps import GameDeps
from app.agent.factory import build_game_master
from app.core.config import Settings
from app.main import create_app


async def _apply_migrations(url: str) -> None:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        for sql in sorted(MIGRATIONS_DIR.glob("V*.sql")):
            await conn.execute(sql.read_text())
    finally:
        await conn.close()


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        asyncio.run(_apply_migrations(url))
        yield url


async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def agent() -> Agent[GameDeps, str]:
    """The real game master; tests swap its model with `agent.override(model=...)`."""
    llm = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost/x",
        family_llm_model="vendor/model-x",
        openrouter_api_key=SecretStr("test-key"),
    )
    return build_game_master(llm)


@pytest.fixture
async def client(postgres_url: str, agent: Agent[GameDeps, str]) -> AsyncIterator[AsyncClient]:
    settings = Settings(database_url=postgres_url, cookie_secure=False)
    async for c in _client(create_app(settings, agent=agent)):
        yield c


@pytest.fixture
async def secure_client(
    postgres_url: str, agent: Agent[GameDeps, str]
) -> AsyncIterator[AsyncClient]:
    settings = Settings(database_url=postgres_url, cookie_secure=True)
    async for c in _client(create_app(settings, agent=agent)):
        yield c


@pytest.fixture
async def client_db_blackholed(agent: Agent[GameDeps, str]) -> AsyncIterator[AsyncClient]:
    blackhole = "postgresql+asyncpg://u:p@10.255.255.1:5432/none"
    async for c in _client(create_app(Settings(database_url=blackhole), agent=agent)):
        yield c


@pytest.fixture
async def client_db_down(agent: Agent[GameDeps, str]) -> AsyncIterator[AsyncClient]:
    dead = "postgresql+asyncpg://u:p@127.0.0.1:1/none"
    async for c in _client(create_app(Settings(database_url=dead), agent=agent)):
        yield c


@pytest.fixture
def db_fetch(postgres_url: str):
    async def run(sql: str, *args):
        conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return run
