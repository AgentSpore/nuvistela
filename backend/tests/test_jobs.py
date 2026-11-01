import uuid
from datetime import timedelta

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


async def test_only_the_current_lease_holder_can_finish_a_job(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    family_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO families (id, title) VALUES (:id, 't')"), {"id": family_id}
        )
        await JobRepository(conn).enqueue("world", family_id, {})
    async with engine.begin() as conn:
        old = await JobRepository(conn).claim(["world"], family_id=family_id)
        await conn.execute(text("UPDATE jobs SET locked_at = now() - interval '1 hour'"))
    async with engine.begin() as conn:
        new = await JobRepository(conn).claim(["world"], family_id=family_id)
    assert old is not None and new is not None
    async with engine.begin() as conn:
        repo = JobRepository(conn)
        assert not await repo.complete(old)
        assert not await repo.fail(old, "x", final=False, retry_in=timedelta(0))
        assert await repo.complete(new)
    await engine.dispose()
