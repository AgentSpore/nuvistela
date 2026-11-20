import asyncio
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.repositories.adventure_repository import AdventureRepository
from app.services.adventure_fallback import open_fallback_quest
from tests.conftest import _client
from tests.test_world_api import adult_with_child

START = "/api/v1/families/{}/adventure"
DONE = "/api/v1/quests/{}/done"
RETRY = "/api/v1/chapters/{}/retry"


async def open_template(c: AsyncClient, adult: dict, fid: str) -> dict:
    """Quest 1 as a stored fallback world leaves it, without running the world worker."""
    app = cast(FastAPI, cast(ASGITransport, c._transport).app)  # the app behind the client
    engine = app.state.engine
    async with engine.begin() as conn:
        await open_fallback_quest(AdventureRepository(conn), UUID(fid), None, "ru")
    return (await c.get(START.format(fid), headers=adult)).json()["quest"]


async def started(c: AsyncClient) -> tuple[dict, dict, str, dict]:
    adult, child, fid, *_ = await adult_with_child(c)
    r = await c.post(START.format(fid), headers=adult, json={"genre": "pirates"})
    assert r.status_code == 200
    return adult, child, fid, r.json()["quest"] or await open_template(c, adult, fid)


async def test_start_queues_the_world_and_opens_no_quest_yet(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    cast(FastAPI, cast(ASGITransport, client._transport).app).state.world_worker = True
    for _ in range(2):  # a second start neither queues another world nor opens a quest
        r = await client.post(START.format(fid), headers=adult, json={"genre": "pirates"})
        assert r.json() == {"world_status": "pending", "quest": None}
    body = (await client.get(START.format(fid), headers=adult)).json()
    assert body == {
        "world": {"status": "pending"},
        "quest": None,
        "chapters": [],
        "chronicle": [],
        "skills": [],
    }
    assert len(await db_fetch("SELECT 1 FROM jobs WHERE family_id = $1", UUID(fid))) == 1
    assert await db_fetch("SELECT 1 FROM quests WHERE family_id = $1", UUID(fid)) == []


async def test_start_twice_keeps_one_quest(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, quest = await started(client)
    again = await client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert again.status_code == 200 and again.json()["quest"]["id"] == quest["id"]
    rows = await db_fetch("SELECT 1 FROM quests WHERE family_id = $1", UUID(fid))
    jobs = await db_fetch("SELECT 1 FROM jobs WHERE family_id = $1", UUID(fid))
    assert len(rows) == 1 and jobs == []  # no worker in this app: fallback world, no job


async def test_start_is_adult_only_and_family_scoped(client: AsyncClient) -> None:
    adult, child, fid, _ = await started(client)
    other, *_ = await adult_with_child(client)
    body = {"genre": "space"}
    assert (await client.post(START.format(fid), headers=child, json=body)).status_code == 403
    assert (await client.post(START.format(fid), headers=other, json=body)).status_code == 404
    assert (await client.get(START.format(fid), headers=other)).status_code == 404


async def test_get_before_start_is_empty(client: AsyncClient) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    body = (await client.get(START.format(fid), headers=adult)).json()
    assert body == {"world": None, "quest": None, "chapters": [], "chronicle": [], "skills": []}


async def test_done_creates_one_chapter_and_one_job(client: AsyncClient, db_fetch) -> None:
    _, child, fid, quest = await started(client)
    r = await client.post(DONE.format(quest["id"]), headers=child, json={"note": "found it"})
    assert r.status_code == 200
    chapter = r.json()["chapter"]
    assert chapter["status"] == "queued" and r.json()["next_quest"] is None
    jobs = await db_fetch("SELECT payload FROM jobs WHERE kind = 'chapter'")
    mine = [j for j in jobs if str(quest["id"]) in j["payload"]]
    assert len(mine) == 1 and "found it" not in mine[0]["payload"]


async def test_done_8_concurrent_one_event_one_chapter_one_job(
    client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, quest = await started(client)
    results = await asyncio.gather(
        *(client.post(DONE.format(quest["id"]), headers=adult, json={}) for _ in range(8))
    )
    assert {r.status_code for r in results} == {200}
    assert len({r.json()["chapter"]["id"] for r in results}) == 1
    qid = UUID(quest["id"])
    assert len(await db_fetch("SELECT 1 FROM quest_events WHERE quest_id = $1", qid)) == 1
    assert len(await db_fetch("SELECT 1 FROM chapters WHERE quest_id = $1", qid)) == 1
    jobs = await db_fetch("SELECT 1 FROM jobs WHERE kind = 'chapter' AND family_id = $1", UUID(fid))
    assert len(jobs) == 1


async def test_done_replay_same_key_returns_same_chapter(client: AsyncClient) -> None:
    adult, _, _, quest = await started(client)
    headers = {**adult, "Idempotency-Key": "k-1"}
    first = await client.post(DONE.format(quest["id"]), headers=headers, json={})
    again = await client.post(DONE.format(quest["id"]), headers=headers, json={})
    assert again.status_code == 200 and again.json() == first.json()


async def test_done_key_reused_on_other_quest_409(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, quest = await started(client)
    headers = {**adult, "Idempotency-Key": "k-2"}
    await client.post(DONE.format(quest["id"]), headers=headers, json={})
    rows = await db_fetch(
        "INSERT INTO quests (family_id, seq, title, description, skill, source)"
        " VALUES ($1, 2, 't', 'd', 's', 'model') RETURNING id",
        UUID(fid),
    )
    r = await client.post(DONE.format(str(rows[0]["id"])), headers=headers, json={})
    assert r.status_code == 409


async def test_done_other_family_or_unknown_quest_is_404(client: AsyncClient) -> None:
    _, _, _, quest = await started(client)
    other, *_ = await adult_with_child(client)
    assert (await client.post(DONE.format(quest["id"]), headers=other, json={})).status_code == 404
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(DONE.format(unknown), headers=other, json={})).status_code == 404


async def test_done_rejects_a_note_over_280_chars(client: AsyncClient) -> None:
    adult, _, _, quest = await started(client)
    r = await client.post(DONE.format(quest["id"]), headers=adult, json={"note": "x" * 281})
    assert r.status_code == 422


async def test_get_after_restart_same_history(
    client: AsyncClient, postgres_url: str, db_fetch
) -> None:
    adult, _, fid, quest = await started(client)
    await client.post(DONE.format(quest["id"]), headers=adult, json={})
    before = (await client.get(START.format(fid), headers=adult)).json()
    app = create_app(Settings(database_url=postgres_url, cookie_secure=False))
    async for fresh in _client(app):
        after = (await fresh.get(START.format(fid), headers=adult)).json()
    assert after == before and before["chapters"][0]["status"] == "queued"


async def test_retry_requeues_delayed_only(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, quest = await started(client)
    chapter = (await client.post(DONE.format(quest["id"]), headers=adult, json={})).json()[
        "chapter"
    ]
    assert (await client.post(RETRY.format(chapter["id"]), headers=adult)).status_code == 409
    await db_fetch(
        "UPDATE chapters SET status = 'delayed_model' WHERE id = $1", UUID(chapter["id"])
    )
    r = await client.post(RETRY.format(chapter["id"]), headers=adult)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    jobs = await db_fetch("SELECT 1 FROM jobs WHERE kind = 'chapter' AND family_id = $1", UUID(fid))
    assert len(jobs) == 2
    other, *_ = await adult_with_child(client)
    assert (await client.post(RETRY.format(chapter["id"]), headers=other)).status_code == 404


async def test_start_does_not_open_a_quest_while_the_chapter_is_pending(
    client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, quest = await started(client)
    await client.post(DONE.format(quest["id"]), headers=adult, json={})
    again = await client.post(START.format(fid), headers=adult, json={"genre": "pirates"})
    assert again.status_code == 200 and again.json()["quest"] is None
    assert len(await db_fetch("SELECT 1 FROM quests WHERE family_id = $1", UUID(fid))) == 1


async def test_delayed_chapter_falls_back_to_template_quest(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, quest = await started(client)
    await client.post(DONE.format(quest["id"]), headers=adult, json={})
    await db_fetch("UPDATE chapters SET status = 'delayed_model' WHERE family_id = $1", UUID(fid))
    body = {"genre": "pirates"}
    first = (await client.post(START.format(fid), headers=adult, json=body)).json()["quest"]
    again = (await client.post(START.format(fid), headers=adult, json=body)).json()["quest"]
    assert first["seq"] == 2 and first["source"] == "template" and again["id"] == first["id"]


async def test_child_cannot_retry_a_chapter(client: AsyncClient, db_fetch) -> None:
    adult, child, fid, quest = await started(client)
    chapter = (await client.post(DONE.format(quest["id"]), headers=adult, json={})).json()[
        "chapter"
    ]
    await db_fetch(
        "UPDATE chapters SET status = 'delayed_model' WHERE id = $1", UUID(chapter["id"])
    )
    assert (await client.post(RETRY.format(chapter["id"]), headers=child)).status_code == 403


async def test_retry_limit_counts_retries_not_first_writes(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, quest = await started(client)
    chapter = (await client.post(DONE.format(quest["id"]), headers=adult, json={})).json()[
        "chapter"
    ]
    for seq in (2, 3):
        rows = await db_fetch(
            "INSERT INTO quests (family_id, seq, title, description, skill, source)"
            " VALUES ($1, $2, 't', 'd', 's', 'model') RETURNING id",
            UUID(fid),
            seq,
        )
        await client.post(DONE.format(str(rows[0]["id"])), headers=adult, json={})
    jobs = await db_fetch("SELECT 1 FROM jobs WHERE kind = 'chapter' AND family_id = $1", UUID(fid))
    assert len(jobs) == 3
    codes = []
    for _ in range(4):
        await db_fetch(
            "UPDATE chapters SET status = 'delayed_model' WHERE id = $1", UUID(chapter["id"])
        )
        codes.append((await client.post(RETRY.format(chapter["id"]), headers=adult)).status_code)
    assert codes == [202, 202, 202, 429]


async def test_retry_that_requeues_nothing_is_409_and_leaves_no_job(
    client: AsyncClient, db_fetch, monkeypatch: pytest.MonkeyPatch
) -> None:
    adult, _, fid, quest = await started(client)
    chapter = (await client.post(DONE.format(quest["id"]), headers=adult, json={})).json()[
        "chapter"
    ]
    await db_fetch(
        "UPDATE chapters SET status = 'delayed_budget' WHERE id = $1", UUID(chapter["id"])
    )

    async def nothing_updated(self: AdventureRepository, chapter_id: UUID, job_id: UUID) -> bool:
        return False

    monkeypatch.setattr(AdventureRepository, "requeue_chapter", nothing_updated)
    r = await client.post(RETRY.format(chapter["id"]), headers=adult)
    assert r.status_code == 409 and "delayed_budget" in r.json()["detail"]
    jobs = await db_fetch("SELECT 1 FROM jobs WHERE kind = 'chapter' AND family_id = $1", UUID(fid))
    assert len(jobs) == 1


async def test_without_a_world_worker_start_stores_the_fallback_and_the_template(
    client: AsyncClient, db_fetch
) -> None:
    """No API key (as here), or WORLD_WORKER_ENABLED=false: nothing would process a job."""
    adult, child, fid, *_ = await adult_with_child(client)
    for _ in range(2):
        r = await client.post(START.format(fid), headers=adult, json={"genre": "space"})
        assert r.status_code == 200 and r.json()["world_status"] == "fallback"
        assert r.json()["quest"]["source"] == "template" and r.json()["quest"]["seq"] == 1
    assert len(await db_fetch("SELECT 1 FROM quests WHERE family_id = $1", UUID(fid))) == 1
    assert await db_fetch("SELECT 1 FROM jobs WHERE family_id = $1", UUID(fid)) == []
    world = (await client.get(f"/api/v1/families/{fid}/world", headers=child)).json()
    assert world["status"] == "fallback" and len(world["world"]["heroes"]) == 2


async def test_disabled_worker_flag_also_stores_the_fallback(postgres_url: str, agent) -> None:
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        cookie_secure=False,
        world_worker_enabled=False,
        openrouter_api_key=SecretStr("k"),
    )
    async for c in _client(create_app(settings, agent=agent)):
        adult, _, fid, *_ = await adult_with_child(c)
        r = await c.post(START.format(fid), headers=adult, json={"genre": "pirates"})
        assert r.json()["world_status"] == "fallback" and r.json()["quest"]["source"] == "template"


async def test_pending_world_without_a_worker_gets_the_fallback_on_start(
    client: AsyncClient, db_fetch
) -> None:
    """Queued before a restart into no-worker mode: nothing would ever process the job."""
    adult, _, fid, *_ = await adult_with_child(client)
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    app.state.world_worker = True
    first = await client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert first.json() == {"world_status": "pending", "quest": None}
    app.state.world_worker = None
    r = await client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert r.json()["world_status"] == "fallback" and r.json()["quest"]["source"] == "template"
    assert len(await db_fetch("SELECT 1 FROM quests WHERE family_id = $1", UUID(fid))) == 1
