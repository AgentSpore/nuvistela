import hashlib
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.repositories.world_scene_repository import WorldSceneRepository
from tests.test_world_api import adult_with_child

SPZ = b"\x1f\x8b\x08fake-splat-bytes"
PANORAMA = b"RIFF\x24\x00\x00\x00WEBPVP8 fake-panorama"
SHA = hashlib.sha256(SPZ).hexdigest()
NOT_FOUND = {"detail": "not found"}


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(postgres_url)
    yield e
    await e.dispose()


async def ready_scene(engine: AsyncEngine, fid: str, job: UUID | None = None) -> UUID:
    job = job or uuid4()
    async with engine.begin() as conn:
        scenes = WorldSceneRepository(conn)
        assert await scenes.create_pending(UUID(fid), job)
        assert await scenes.mark_ready(UUID(fid), job, SPZ, PANORAMA)
    return job


async def test_owner_gets_spz_with_cache_headers(client: AsyncClient, engine) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    await ready_scene(engine, fid)
    r = await client.get(f"/api/v1/media/{SHA}.spz", headers=adult)
    assert r.status_code == 200
    assert r.content == SPZ
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert r.headers["etag"] == f'"{SHA}"'
    r = await client.get(f"/api/v1/media/{SHA}.spz", headers={**adult, "If-None-Match": f'"{SHA}"'})
    assert r.status_code == 304


async def test_everything_else_is_the_same_404(client: AsyncClient, engine) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    await ready_scene(engine, fid)
    other, *_ = await adult_with_child(client)
    url = f"/api/v1/media/{SHA}.spz"
    responses = [
        await client.get(url, headers=other),
        await client.get(url),
        await client.get(url, headers={"Cookie": "bumbli_session=forged"}),
        await client.get(f"/api/v1/media/{'a' * 64}.spz", headers=adult),
        await client.get(f"/api/v1/media/{SHA.upper()}.spz", headers=adult),
        await client.get(f"/api/v1/media/{SHA[:-1]}.spz", headers=adult),
        await client.get(f"/api/v1/media/{'z' * 64}.spz", headers=adult),
        await client.get("/api/v1/media/..etc.spz", headers=adult),
        await client.get(url, headers={**other, "If-None-Match": f'"{SHA}"'}),
    ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert all(r.json() == NOT_FOUND for r in responses)


async def test_spz_sha_is_not_served_as_webp_and_back(client: AsyncClient, engine) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    await ready_scene(engine, fid)
    r = await client.get(f"/api/v1/media/{SHA}.webp", headers=adult)
    assert r.status_code == 404


async def test_pending_and_failed_scenes_are_404(client: AsyncClient, engine) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    job = uuid4()
    async with engine.begin() as conn:
        scenes = WorldSceneRepository(conn)
        assert await scenes.create_pending(UUID(fid), job)
        assert await scenes.mark_failed(UUID(fid), job)
        assert await scenes.mark_ready(UUID(fid), job, SPZ, PANORAMA) is False
    r = await client.get(f"/api/v1/media/{SHA}.spz", headers=adult)
    assert r.status_code == 404


async def test_repository_transitions(engine) -> None:
    fid = await _family(engine)
    job = uuid4()
    async with engine.begin() as conn:
        scenes = WorldSceneRepository(conn)
        assert await scenes.mark_ready(fid, job, SPZ, PANORAMA) is False  # nothing ordered
        assert await scenes.create_pending(fid, job) is True
        assert await scenes.create_pending(fid, job) is False  # idempotent
        assert await scenes.mark_ready(fid, job, SPZ, PANORAMA) is True
        assert await scenes.mark_ready(fid, job, b"again", PANORAMA) is False
        assert await scenes.mark_failed(fid, job) is False
        assert await scenes.ready_spz(fid, SHA) == SPZ
        assert await scenes.ready_spz(uuid4(), SHA) is None


async def test_list_never_selects_bytes(engine) -> None:
    fid = await _family(engine)
    job = uuid4()
    async with engine.begin() as conn:
        scenes = WorldSceneRepository(conn)
        await scenes.create_pending(fid, job)
        await scenes.mark_ready(fid, job, SPZ, PANORAMA)
    seen: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    async with engine.begin() as conn:
        listed = await WorldSceneRepository(conn).list_for_family(fid)
    assert [(s.world_job_id, s.status, s.sha) for s in listed] == [(job, "ready", SHA)]
    assert seen
    assert all("spz" not in s.lower() and "panorama" not in s.lower() for s in seen)


async def test_deleting_the_family_removes_its_scenes(
    client: AsyncClient, engine, db_fetch
) -> None:
    _, _, fid, *_ = await adult_with_child(client)
    await ready_scene(engine, fid)
    await db_fetch("DELETE FROM families WHERE id = $1", UUID(fid))
    assert await db_fetch("SELECT 1 FROM world_scenes WHERE family_id = $1", UUID(fid)) == []


async def test_check_rejects_content_that_does_not_match_the_status(
    client: AsyncClient, db_fetch
) -> None:
    _, _, fid, *_ = await adult_with_child(client)
    insert = (
        "INSERT INTO world_scenes (family_id, world_job_id, status, sha256, spz, panorama)"
        " VALUES ($1, $2, $3, $4, $5, $6)"
    )
    bad = [
        ("ready", None, None, None),
        ("ready", SHA, SPZ, None),
        ("ready", SHA, None, PANORAMA),
        ("ready", "not-a-sha", SPZ, PANORAMA),
        ("pending", SHA, SPZ, PANORAMA),
        ("failed", None, SPZ, None),
        ("done", None, None, None),
    ]
    for status, sha, spz, pano in bad:
        with pytest.raises(asyncpg.CheckViolationError):
            await db_fetch(insert, UUID(fid), uuid4(), status, sha, spz, pano)
    await db_fetch(insert, UUID(fid), uuid4(), "ready", SHA, SPZ, PANORAMA)
    await db_fetch(insert, UUID(fid), uuid4(), "pending", None, None, None)


async def _family(engine: AsyncEngine) -> UUID:
    async with engine.begin() as conn:
        row = await conn.execute(text("INSERT INTO families (title) VALUES ('T') RETURNING id"))
        return row.scalar_one()
