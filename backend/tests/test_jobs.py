import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.repositories.job_repository import JobRepository


async def test_claim_skips_locked_rows(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    family_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, title) VALUES (:id, 't')"), {"id": family_id}
        )
        await JobRepository(conn).enqueue("world", family_id, {})
    async with engine.begin() as c1, engine.begin() as c2:
        first = await JobRepository(c1).claim(["world"], family_id=family_id)
        second = await JobRepository(c2).claim(["world"], family_id=family_id)
    await engine.dispose()
    assert first is not None and first.attempts == 1
    assert second is None
