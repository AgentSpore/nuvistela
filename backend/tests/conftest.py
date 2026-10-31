from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17", driver="asyncpg") as pg:
        yield pg.get_connection_url()


async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client(postgres_url: str) -> AsyncIterator[AsyncClient]:
    async for c in _client(create_app(Settings(database_url=postgres_url))):
        yield c


@pytest.fixture
async def client_db_down() -> AsyncIterator[AsyncClient]:
    dead = "postgresql+asyncpg://u:p@127.0.0.1:1/none"
    async for c in _client(create_app(Settings(database_url=dead))):
        yield c
