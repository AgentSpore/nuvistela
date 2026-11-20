import hashlib
from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.domain.world import Hero, Location, World
from app.main import create_app
from app.repositories.image_repository import ImageRepository
from app.repositories.world_repository import WorldRepository
from tests.conftest import _client
from tests.test_world_api import PATH, adult_with_child, set_worker
from tests.test_world_images import DATA

SHARE = "/api/v1/families/{}/world/share"
PUBLIC = "/api/v1/share/{}"
NOT_FOUND = {"detail": "not found"}


@pytest.fixture
async def client(postgres_url: str, agent) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_url=postgres_url, cookie_secure=False, share_token_key=SecretStr("k" * 32)
    )
    async for c in _client(create_app(settings, agent=agent)):
        set_worker(c, True)
        yield c


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(postgres_url)
    yield e
    await e.dispose()


def world_titled(title: str) -> World:
    return World(
        title=title,
        setting="A bay",
        tone="calm",
        locations=[Location(name=f"P{i}", description="d") for i in range(4)],
        heroes=[Hero(member_id=UUID(int=1), hero_class="c", trait="t", skill="s")],
        prologue="Once",
    )


async def ready_world(
    client: AsyncClient,
    engine: AsyncEngine,
    db_fetch,
    title: str = "Quiet Bay",
    genre: str = "space",
    cover: bool = True,
) -> tuple[dict, dict, str, UUID]:
    adult, child, fid, *_ = await adult_with_child(client)
    body = {"genre": genre, **({"custom_genre": "Dragons of Anya"} if genre == "custom" else {})}
    assert (await client.post(PATH.format(fid), headers=adult, json=body)).status_code == 202
    job = (await db_fetch("SELECT job_id FROM worlds WHERE family_id = $1", UUID(fid)))[0]["job_id"]
    async with engine.begin() as conn:
        assert await WorldRepository(conn).save(UUID(fid), "ready", world_titled(title), job)
        images = ImageRepository(conn)
        if cover:
            assert await images.create_pending(UUID(fid), job, "a quiet harbor")
            assert await images.mark_ready(UUID(fid), job, DATA)
    return adult, child, fid, job


async def shared(client, engine, db_fetch, **kw) -> tuple[dict, str, str]:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, **kw)
    r = await client.post(SHARE.format(fid), headers=adult)
    assert r.status_code == 200
    return adult, fid, r.json()["token"]


async def test_child_and_other_family_are_refused(client, engine, db_fetch) -> None:
    adult, child, fid, _ = await ready_world(client, engine, db_fetch)
    other, *_ = await adult_with_child(client)
    assert (await client.post(SHARE.format(fid), headers=child)).status_code == 403
    assert (await client.post(SHARE.format(fid), headers=other)).status_code == 404
    assert (await client.post(SHARE.format(fid))).status_code == 401
    assert (await client.delete(SHARE.format(fid), headers=child)).status_code == 403
    assert (await client.delete(SHARE.format(fid), headers=other)).status_code == 404


async def test_no_ready_cover_is_409(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, cover=False)
    assert (await client.post(SHARE.format(fid), headers=adult)).status_code == 409


async def test_repeat_gives_the_same_token(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    again = await client.post(SHARE.format(fid), headers=adult)
    assert again.json() == {"token": token, "created": False}
    assert len(await db_fetch("SELECT 1 FROM world_shares WHERE family_id=$1", UUID(fid))) == 1


async def test_token_is_not_stored_in_clear(client, engine, db_fetch) -> None:
    _, fid, token = await shared(client, engine, db_fetch)
    rows = await db_fetch("SELECT * FROM world_shares WHERE family_id = $1", UUID(fid))
    assert rows[0]["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in "".join(str(v) for v in rows[0].values())
    assert len(token) >= 22


async def test_public_json_has_exactly_the_allowed_keys(client, engine, db_fetch) -> None:
    _, _, token = await shared(client, engine, db_fetch)
    r = await client.get(PUBLIC.format(token))
    assert r.status_code == 200
    assert r.json() == {
        "title": "Quiet Bay",
        "genre": "space",
        "cover_url": f"/api/v1/share/{token}/cover.webp",
        "quests_done": 0,
        "chapters": 0,
    }
    assert "set-cookie" not in r.headers


async def seed_story(engine: AsyncEngine, fid: str, done: int, open_: int, ready: int) -> None:
    """Quests from seq 100 (done first, then open) and a chapter per done quest, `ready` ready."""
    async with engine.begin() as conn:
        for i in range(done + open_):
            status = "done" if i < done else "open"
            quest = (
                await conn.execute(
                    text(
                        "INSERT INTO quests (family_id, seq, title, description, skill, source,"
                        " status) VALUES (:f, :s, 'q', 'd', 'k', 'model', :st) RETURNING id"
                    ),
                    {"f": UUID(fid), "s": 100 + i, "st": status},
                )
            ).scalar_one()
            if i < done:
                await conn.execute(
                    text(
                        "INSERT INTO chapters (family_id, quest_id, seq, status)"
                        " VALUES (:f, :q, :s, :st)"
                    ),
                    {
                        "f": UUID(fid),
                        "q": quest,
                        "s": 100 + i,
                        "st": "ready" if i < ready else "queued",
                    },
                )


async def test_counters_count_only_the_shared_family(client, engine, db_fetch) -> None:
    _, fid, token = await shared(client, engine, db_fetch)
    _, other_fid, _ = await shared(client, engine, db_fetch)
    await seed_story(engine, fid, done=3, open_=0, ready=2)
    await seed_story(engine, other_fid, done=4, open_=0, ready=4)
    body = (await client.get(PUBLIC.format(token))).json()
    assert (body["quests_done"], body["chapters"]) == (3, 2)


async def test_open_quests_and_unwritten_chapters_do_not_count(client, engine, db_fetch) -> None:
    _, fid, token = await shared(client, engine, db_fetch)
    await seed_story(engine, fid, done=1, open_=1, ready=0)
    body = (await client.get(PUBLIC.format(token))).json()
    assert (body["quests_done"], body["chapters"]) == (1, 0)


async def test_cover_bytes_are_public_and_cached_five_minutes(client, engine, db_fetch) -> None:
    _, _, token = await shared(client, engine, db_fetch)
    r = await client.get(f"/api/v1/share/{token}/cover.webp")
    assert r.status_code == 200
    assert r.content == DATA
    assert r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "public, max-age=300"


@pytest.mark.parametrize("title", ["Bobby's Bay", "The BOBBY bay", "Бухта Anya", "Quiet 7 Bay"])
async def test_title_with_a_member_name_is_replaced(client, engine, db_fetch, title) -> None:
    _, _, token = await shared(client, engine, db_fetch, title=title)
    assert (await client.get(PUBLIC.format(token))).json()["title"] is None


async def test_name_inside_another_word_is_not_caught(client, engine, db_fetch) -> None:
    _, _, token = await shared(client, engine, db_fetch, title="Bobbyland Harbor")
    assert (await client.get(PUBLIC.format(token))).json()["title"] == "Bobbyland Harbor"


async def test_custom_genre_text_is_never_stored_or_returned(client, engine, db_fetch) -> None:
    _, fid, token = await shared(client, engine, db_fetch, genre="custom")
    r = await client.get(PUBLIC.format(token))
    assert r.json()["genre"] == "custom"
    assert "Dragons" not in r.text
    rows = await db_fetch("SELECT * FROM world_shares WHERE family_id = $1", UUID(fid))
    assert "Dragons" not in str(dict(rows[0]))


async def test_revoked_unknown_and_malformed_are_the_same_404(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    assert (await client.delete(SHARE.format(fid), headers=adult)).status_code == 204
    assert (await client.delete(SHARE.format(fid), headers=adult)).status_code == 204
    paths = [token, "A" * 22, "short", "x" * 200, "a%20b", token.upper()]
    responses = [await client.get(PUBLIC.format(p)) for p in paths]
    responses += [await client.get(PUBLIC.format(p) + "/cover.webp") for p in paths]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert [r.json() for r in responses] == [NOT_FOUND] * len(responses)
    assert all("cache-control" not in r.headers for r in responses)


async def test_new_link_after_revoke_is_a_different_token(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    await client.delete(SHARE.format(fid), headers=adult)
    r = await client.post(SHARE.format(fid), headers=adult)
    assert r.json()["created"] is True
    assert r.json()["token"] != token


async def test_regenerated_world_keeps_showing_the_old_cover(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    assert (await client.post(PATH.format(fid) + "/regenerate", headers=adult)).status_code == 202
    new_job = (await db_fetch("SELECT job_id FROM worlds WHERE family_id=$1", UUID(fid)))[0][0]
    async with engine.begin() as conn:
        assert await WorldRepository(conn).save(UUID(fid), "ready", world_titled("New"), new_job)
        images = ImageRepository(conn)
        assert await images.create_pending(UUID(fid), new_job, "another")
        assert await images.mark_ready(UUID(fid), new_job, DATA + b"new")
    r = await client.get(PUBLIC.format(token))
    assert r.json()["title"] == "Quiet Bay"
    assert (await client.get(f"/api/v1/share/{token}/cover.webp")).content == DATA
    # The new world is a new version: it gets its own link; revoking turns both off.
    second = await client.post(SHARE.format(fid), headers=adult)
    assert second.json()["created"] is True
    assert second.json()["token"] != token
    await client.delete(SHARE.format(fid), headers=adult)
    assert (await client.get(PUBLIC.format(token))).status_code == 404
    assert (await client.get(PUBLIC.format(second.json()["token"]))).status_code == 404


async def test_deleting_the_family_deletes_its_shares(client, engine, db_fetch) -> None:
    _, fid, _ = await shared(client, engine, db_fetch)
    await db_fetch("DELETE FROM families WHERE id = $1", UUID(fid))
    assert await db_fetch("SELECT 1 FROM world_shares WHERE family_id=$1", UUID(fid)) == []


async def test_eleventh_new_link_in_a_day_is_429(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch)
    codes = []
    for _ in range(11):
        codes.append((await client.post(SHARE.format(fid), headers=adult)).status_code)
        await client.delete(SHARE.format(fid), headers=adult)
    assert codes == [200] * 10 + [429]


async def test_without_a_key_sharing_is_unavailable(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch)
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    app.state.settings.share_token_key = None
    assert (await client.post(SHARE.format(fid), headers=adult)).status_code == 409


@pytest.mark.parametrize("blank", ["", "   ", " \t\n "])
async def test_blank_key_means_sharing_off(postgres_url, agent, engine, db_fetch, blank) -> None:
    settings = Settings(database_url=postgres_url, cookie_secure=False, share_token_key=blank)
    assert settings.share_token_key is None
    async for c in _client(create_app(settings, agent=agent)):
        set_worker(c, True)
        adult, _, fid, _ = await ready_world(c, engine, db_fetch)
        assert (await c.post(SHARE.format(fid), headers=adult)).status_code == 409


def test_padded_short_key_is_refused_after_stripping() -> None:
    padded = " " * 20 + "k" * 20 + " " * 20
    with pytest.raises(ValueError, match="at least 32") as err:
        Settings(database_url="postgresql+asyncpg://x/y", share_token_key=padded)
    assert "kkkk" not in str(err.value)


def test_padding_around_a_valid_key_is_not_part_of_the_key() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://x/y", share_token_key="  " + "k" * 32 + "\n"
    )
    assert settings.share_token_key is not None
    assert settings.share_token_key.get_secret_value() == "k" * 32


def test_short_key_is_refused_without_echoing_it() -> None:
    with pytest.raises(ValueError, match="at least 32") as err:
        Settings(database_url="postgresql+asyncpg://x/y", share_token_key="short-secret")
    assert "short-secret" not in str(err.value)


async def test_deleting_the_sharing_member_keeps_the_link(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    await db_fetch("DELETE FROM members WHERE family_id = $1 AND role = 'adult'", UUID(fid))
    rows = await db_fetch("SELECT created_by FROM world_shares WHERE family_id = $1", UUID(fid))
    assert [r["created_by"] for r in rows] == [None]
    assert (await client.get(PUBLIC.format(token))).status_code == 200


async def test_revoking_one_family_leaves_another_family_link(client, engine, db_fetch) -> None:
    adult_a, fid_a, token_a = await shared(client, engine, db_fetch)
    _, _, token_b = await shared(client, engine, db_fetch)
    assert (await client.delete(SHARE.format(fid_a), headers=adult_a)).status_code == 204
    assert (await client.get(PUBLIC.format(token_a))).status_code == 404
    assert (await client.get(PUBLIC.format(token_b))).status_code == 200


async def test_status_is_adult_only_and_family_scoped(client, engine, db_fetch) -> None:
    adult, child, fid, _ = await ready_world(client, engine, db_fetch)
    other, *_ = await adult_with_child(client)
    assert (await client.get(SHARE.format(fid), headers=child)).status_code == 403
    assert (await client.get(SHARE.format(fid), headers=other)).status_code == 404
    assert (await client.get(SHARE.format(fid))).status_code == 401
    assert (await client.get(SHARE.format(fid), headers=adult)).status_code == 200


@pytest.mark.parametrize("title", ["Bobby's Bay", "Quiet 7 Bay"])
async def test_status_title_is_vetted_like_the_public_card(client, engine, db_fetch, title) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, title=title)
    assert (await client.get(SHARE.format(fid), headers=adult)).json()["title"] is None


async def test_status_has_the_title_genre_and_token_only(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, genre="space")
    before = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert before == {
        "title": "Quiet Bay",
        "genre": "space",
        "token": None,
        "other_active": False,
        "quests_done": 0,
        "chapters": 0,
    }
    token = (await client.post(SHARE.format(fid), headers=adult)).json()["token"]
    after = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert after == {
        "title": "Quiet Bay",
        "genre": "space",
        "token": token,
        "other_active": False,
        "quests_done": 0,
        "chapters": 0,
    }
    assert (await client.delete(SHARE.format(fid), headers=adult)).status_code == 204
    gone = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert gone["token"] is None


async def test_status_never_returns_custom_genre_text(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, genre="custom")
    body = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert body["genre"] == "custom" and "Anya" not in str(body)


async def test_status_without_key_has_no_token(client, engine, db_fetch) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch)
    await client.post(SHARE.format(fid), headers=adult)
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    app.state.settings.share_token_key = None
    assert (await client.get(SHARE.format(fid), headers=adult)).json()["token"] is None


async def test_status_without_a_ready_world_is_409(client, engine, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(client)  # no world yet
    assert (await client.get(SHARE.format(fid), headers=adult)).status_code == 409


async def test_status_of_an_active_link_is_the_stored_card_not_a_new_vetting(
    client, engine, db_fetch
) -> None:
    adult, fid, token = await shared(client, engine, db_fetch, title="Quiet Bay")
    added = await client.post(
        f"/api/v1/families/{fid}/members",
        headers=adult,
        json={"display_name": "Quiet", "age_band": "6-9", "role": "child", "interests": []},
    )
    assert added.status_code == 201
    status = (await client.get(SHARE.format(fid), headers=adult)).json()
    public = (await client.get(PUBLIC.format(token))).json()
    assert status["title"] == public["title"] == "Quiet Bay"
    assert status["genre"] == public["genre"]


async def test_status_reports_an_old_version_link_it_cannot_return(
    client, engine, db_fetch
) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    assert (await client.post(PATH.format(fid) + "/regenerate", headers=adult)).status_code == 202
    new_job = (await db_fetch("SELECT job_id FROM worlds WHERE family_id=$1", UUID(fid)))[0][0]
    async with engine.begin() as conn:
        assert await WorldRepository(conn).save(UUID(fid), "ready", world_titled("New"), new_job)
    status = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert status["token"] is None and status["other_active"] is True
    assert (await client.get(PUBLIC.format(token))).status_code == 200
    await client.delete(SHARE.format(fid), headers=adult)
    assert (await client.get(SHARE.format(fid), headers=adult)).json()["other_active"] is False


async def test_status_without_key_still_reports_the_active_link(client, engine, db_fetch) -> None:
    adult, fid, _ = await shared(client, engine, db_fetch)
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    app.state.settings.share_token_key = None
    status = (await client.get(SHARE.format(fid), headers=adult)).json()
    assert status["token"] is None and status["other_active"] is True


async def kind_count(db_fetch, kind: str) -> int:
    rows = await db_fetch("SELECT count(*) FROM pilot_events WHERE kind = $1", kind)
    return rows[0]["count"]


async def test_created_and_revoked_are_counted_once_per_real_change(
    client, engine, db_fetch
) -> None:
    created, revoked = [await kind_count(db_fetch, k) for k in ("share_created", "share_revoked")]
    adult, fid, _ = await shared(client, engine, db_fetch)
    assert (await client.post(SHARE.format(fid), headers=adult)).json()["created"] is False
    assert await kind_count(db_fetch, "share_created") == created + 1
    assert (await client.delete(SHARE.format(fid), headers=adult)).status_code == 204
    assert (await client.delete(SHARE.format(fid), headers=adult)).status_code == 204
    assert await kind_count(db_fetch, "share_revoked") == revoked + 1


async def test_refused_requests_record_no_share_event(client, engine, db_fetch) -> None:
    adult, child, fid, _ = await ready_world(client, engine, db_fetch, cover=False)
    before = [await kind_count(db_fetch, k) for k in ("share_created", "share_revoked")]
    assert (await client.post(SHARE.format(fid), headers=child)).status_code == 403
    assert (await client.post(SHARE.format(fid), headers=adult)).status_code == 409
    assert (await client.delete(SHARE.format(fid), headers=child)).status_code == 403
    after = [await kind_count(db_fetch, k) for k in ("share_created", "share_revoked")]
    assert after == before


async def test_share_events_carry_no_session_token_or_family(client, engine, db_fetch) -> None:
    _, fid, token = await shared(client, engine, db_fetch)
    rows = await db_fetch("SELECT * FROM pilot_events WHERE kind = 'share_created'")
    assert all(r["session_id"] is None and r["intent"] is None for r in rows)
    assert not any(token in str(v) or fid in str(v) for r in rows for v in r.values())


@pytest.mark.parametrize(
    ("title", "kept"), [("Барсик и тайна маяка", False), ("Город улиток", True)]
)
async def test_title_with_a_name_from_the_own_description_is_dropped(
    client, engine, db_fetch, title, kept
) -> None:
    adult, _, fid, _ = await ready_world(client, engine, db_fetch, title=title, genre="custom")
    desc = "Наша дача в Комарово, рыжий кот Барсик" if not kept else "город на спинах улиток"
    await db_fetch("UPDATE worlds SET custom_genre = $2 WHERE family_id = $1", UUID(fid), desc)
    got = (await client.get(SHARE.format(fid), headers=adult)).json()["title"]
    assert got == (title if kept else None)


async def test_sender_preview_counts_match_the_public_card(client, engine, db_fetch) -> None:
    adult, fid, token = await shared(client, engine, db_fetch)
    _, other_fid, _ = await shared(client, engine, db_fetch)
    await seed_story(engine, fid, done=2, open_=1, ready=1)
    await seed_story(engine, other_fid, done=5, open_=0, ready=5)
    status = (await client.get(SHARE.format(fid), headers=adult)).json()
    public = (await client.get(PUBLIC.format(token))).json()
    assert (status["quests_done"], status["chapters"]) == (2, 1)
    assert (public["quests_done"], public["chapters"]) == (2, 1)
