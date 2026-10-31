import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer

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
async def client(postgres_url: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(database_url=postgres_url, cookie_secure=False)
    async for c in _client(create_app(settings)):
        yield c


@pytest.fixture
async def secure_client(postgres_url: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(database_url=postgres_url, cookie_secure=True)
    async for c in _client(create_app(settings)):
        yield c


@pytest.fixture
async def client_db_blackholed() -> AsyncIterator[AsyncClient]:
    blackhole = "postgresql+asyncpg://u:p@10.255.255.1:5432/none"
    async for c in _client(create_app(Settings(database_url=blackhole))):
        yield c


@pytest.fixture
async def client_db_down() -> AsyncIterator[AsyncClient]:
    dead = "postgresql+asyncpg://u:p@127.0.0.1:1/none"
    async for c in _client(create_app(Settings(database_url=dead))):
        yield c
