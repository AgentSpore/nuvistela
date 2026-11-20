import hashlib
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.repositories.image_repository import ImageRepository
from tests.test_world_api import PATH, adult_with_child, set_worker

DATA = b"RIFF\x24\x00\x00\x00WEBPVP8 fake-picture-bytes"
SHA = hashlib.sha256(DATA).hexdigest()
NOT_FOUND = {"detail": "not found"}


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(postgres_url)
    yield e
    await e.dispose()


@pytest.fixture(autouse=True)
def worker_runs(client: AsyncClient) -> None:
    set_worker(client, True)


async def world_of_new_family(client: AsyncClient, db_fetch) -> tuple[dict, str, UUID]:
    """A family whose world is requested: returns the adult's headers, family id, world job id."""
    adult, _, fid, *_ = await adult_with_child(client)
    r = await client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    assert r.status_code == 202
    return (
        adult,
        fid,
        (await db_fetch("SELECT job_id FROM worlds WHERE family_id = $1", UUID(fid)))[0]["job_id"],
    )


async def order_cover(engine: AsyncEngine, fid: str, job: UUID, *, ready: bool = False) -> None:
    async with engine.begin() as conn:
        images = ImageRepository(conn)
        assert await images.create_pending(UUID(fid), job, "a quiet harbor at dusk")
        if ready:
            assert await images.mark_ready(UUID(fid), job, DATA)


async def test_owner_gets_bytes_with_cache_headers(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    r = await client.get(f"/api/v1/media/{SHA}.webp", headers=adult)
    assert r.status_code == 200
    assert r.content == DATA
    assert r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert r.headers["etag"] == f'"{SHA}"'


@pytest.mark.parametrize("header", [f'"{SHA}"', f'W/"{SHA}"', f'"other", "{SHA}"', "*"])
async def test_if_none_match_gives_304(client: AsyncClient, engine, db_fetch, header) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    r = await client.get(f"/api/v1/media/{SHA}.webp", headers={**adult, "If-None-Match": header})
    assert r.status_code == 304
    assert r.content == b""
    assert r.headers["etag"] == f'"{SHA}"'


async def test_stale_etag_gets_the_bytes(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    r = await client.get(f"/api/v1/media/{SHA}.webp", headers={**adult, "If-None-Match": '"0123"'})
    assert r.status_code == 200


async def test_everything_else_is_the_same_404(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    other, *_ = await adult_with_child(client)
    url = f"/api/v1/media/{SHA}.webp"
    responses = [
        await client.get(url, headers=other),  # another family
        await client.get(url),  # anonymous
        await client.get(url, headers={"Cookie": "bumbli_session=forged"}),  # unknown session
        await client.get(f"/api/v1/media/{'a' * 64}.webp", headers=adult),  # unknown sha
        await client.get(f"/api/v1/media/{SHA.upper()}.webp", headers=adult),  # not lowercase
        await client.get(f"/api/v1/media/{SHA[:-1]}.webp", headers=adult),  # too short
        await client.get(f"/api/v1/media/{'z' * 64}.webp", headers=adult),  # not hex
        await client.get("/api/v1/media/..etc.webp", headers=adult),
    ]
    # A matching If-None-Match must not turn a non-owner's 404 into a 304.
    for header in (f'"{SHA}"', "*"):
        cond = {"If-None-Match": header}
        responses += [
            await client.get(url, headers={**other, **cond}),
            await client.get(url, headers=cond),
            await client.get(url, headers={"Cookie": "bumbli_session=forged", **cond}),
        ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert all(r.json() == NOT_FOUND for r in responses)
    assert all("etag" not in r.headers for r in responses)


async def test_head_is_405_for_everyone(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    other, *_ = await adult_with_child(client)
    url = f"/api/v1/media/{SHA}.webp"
    codes = [(await client.head(url, headers=h)).status_code for h in (adult, other, {})]
    assert codes == [405, 405, 405]  # no HEAD route: existence is not revealed


async def test_pending_and_failed_rows_are_404(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job)  # pending: no sha exists to ask for
    async with engine.begin() as conn:
        assert await ImageRepository(conn).mark_failed(UUID(fid), job)
    # A sha somebody guessed still finds nothing for a failed row.
    r = await client.get(f"/api/v1/media/{SHA}.webp", headers=adult)
    assert r.status_code == 404
    assert r.json() == NOT_FOUND


async def test_cover_is_null_without_a_row(client: AsyncClient, db_fetch) -> None:
    adult, fid, _ = await world_of_new_family(client, db_fetch)
    body = (await client.get(PATH.format(fid), headers=adult)).json()
    assert body["cover"] is None


async def test_cover_pending_ready_failed(client: AsyncClient, engine, db_fetch) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job)
    assert (await client.get(PATH.format(fid), headers=adult)).json()["cover"] == {
        "status": "pending",
        "url": None,
        "deferred": False,
    }
    async with engine.begin() as conn:
        assert await ImageRepository(conn).mark_ready(UUID(fid), job, DATA)
    assert (await client.get(PATH.format(fid), headers=adult)).json()["cover"] == {
        "status": "ready",
        "url": f"/api/v1/media/{SHA}.webp",
        "deferred": False,
    }
    adult2, fid2, job2 = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid2, job2)
    async with engine.begin() as conn:
        assert await ImageRepository(conn).mark_failed(UUID(fid2), job2)
    assert (await client.get(PATH.format(fid2), headers=adult2)).json()["cover"] == {
        "status": "failed",
        "url": None,
        "deferred": False,
    }


async def test_regenerate_hides_the_previous_worlds_cover(
    client: AsyncClient, engine, db_fetch
) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    r = await client.post(PATH.format(fid) + "/regenerate", headers=adult)
    assert r.status_code == 202
    assert r.json()["cover"] is None
    assert (await client.get(PATH.format(fid), headers=adult)).json()["cover"] is None
    # The old row is kept for its own world version, only not shown for the new one.
    rows = await db_fetch("SELECT count(*) AS n FROM world_images WHERE family_id = $1", UUID(fid))
    assert rows[0]["n"] == 1


async def test_repository_writes_report_whether_a_row_changed(engine) -> None:
    fid = await _bare_family(engine)
    job = uuid4()
    async with engine.begin() as conn:
        images = ImageRepository(conn)
        assert await images.mark_ready(fid, job, DATA) is False  # nothing ordered
        assert await images.create_pending(fid, job, "p") is True
        assert await images.create_pending(fid, job, "other") is False  # idempotent
        assert await images.mark_ready(fid, job, DATA) is True
        assert await images.mark_ready(fid, job, b"again") is False  # no longer pending
        assert await images.mark_failed(fid, job) is False
        assert await images.ready_bytes(fid, SHA) == DATA
        assert await images.ready_bytes(uuid4(), SHA) is None


async def test_status_read_never_selects_bytes(engine) -> None:
    assert "bytes" not in ImageRepository._COVER_STATE.lower()
    seen: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    async with engine.begin() as conn:
        await ImageRepository(conn).cover_state(uuid4())
    assert seen
    assert all("bytes" not in s.lower() for s in seen)


async def test_deleting_the_family_removes_its_images(
    client: AsyncClient, engine, db_fetch
) -> None:
    _, fid, job = await world_of_new_family(client, db_fetch)
    await order_cover(engine, fid, job, ready=True)
    await db_fetch("DELETE FROM families WHERE id = $1", UUID(fid))
    rows = await db_fetch("SELECT 1 FROM world_images WHERE family_id = $1", UUID(fid))
    assert rows == []


async def test_check_rejects_content_that_does_not_match_the_status(
    client: AsyncClient, db_fetch
) -> None:
    _, fid, job = await world_of_new_family(client, db_fetch)
    insert = (
        "INSERT INTO world_images (family_id, world_job_id, kind, prompt, status, sha256, bytes)"
        " VALUES ($1, $2, 'cover', 'p', $3, $4, $5)"
    )
    bad = [
        ("ready", None, None),  # ready without content
        ("ready", SHA, None),
        ("ready", "not-a-sha", DATA),
        ("pending", SHA, DATA),  # content without being ready
        ("failed", None, DATA),
        ("failed", SHA, None),
    ]
    for status, sha, data in bad:
        with pytest.raises(asyncpg.CheckViolationError):
            await db_fetch(insert, UUID(fid), uuid4(), status, sha, data)
    await db_fetch(insert, UUID(fid), uuid4(), "ready", SHA, DATA)
    await db_fetch(insert, UUID(fid), uuid4(), "pending", None, None)
    with pytest.raises(asyncpg.CheckViolationError):  # only the cover kind exists
        await db_fetch(
            "INSERT INTO world_images (family_id, world_job_id, kind, prompt)"
            " VALUES ($1, $2, 'sheet', 'p')",
            UUID(fid),
            uuid4(),
        )


async def _bare_family(engine: AsyncEngine) -> UUID:
    async with engine.begin() as conn:
        row = await conn.execute(text("INSERT INTO families (title) VALUES ('T') RETURNING id"))
        return row.scalar_one()


async def test_only_the_job_of_the_shown_milestone_marks_a_cover_deferred(
    client: AsyncClient, engine, db_fetch
) -> None:
    adult, fid, job = await world_of_new_family(client, db_fetch)
    async with engine.begin() as conn:
        images = ImageRepository(conn)
        for n in (1, 2):
            assert await images.create_pending(UUID(fid), job, "a harbor", n)
    midnight = "(date_trunc('day', now() AT TIME ZONE 'UTC') + interval '1 day') AT TIME ZONE 'UTC'"
    await db_fetch(
        "INSERT INTO jobs (kind, family_id, payload, next_run_at)"
        f" VALUES ('image', $1, $2::jsonb, {midnight})",
        UUID(fid),
        f'{{"world_job_id": "{job}", "milestone_no": 1}}',
    )
    got = (await client.get(PATH.format(fid), headers=adult)).json()["cover"]
    assert got["status"] == "pending" and got["deferred"] is False  # milestone 2 is shown
    await db_fetch(
        "INSERT INTO jobs (kind, family_id, payload, next_run_at)"
        f" VALUES ('image', $1, $2::jsonb, {midnight})",
        UUID(fid),
        f'{{"world_job_id": "{job}", "milestone_no": 2}}',
    )
    got = (await client.get(PATH.format(fid), headers=adult)).json()["cover"]
    assert got["deferred"] is True
