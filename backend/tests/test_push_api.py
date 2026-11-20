from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent

from app.agent.deps import GameDeps
from app.core.config import Settings
from app.main import create_app
from tests.conftest import _client
from tests.test_adventure_api import START
from tests.test_world_api import adult_with_child

KEY = "/api/v1/push/key"
SUBS = "/api/v1/push/subscriptions"
ADULT_BODY = {"display_name": "Papa", "age_band": "adult", "role": "adult"}
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def sub_body(endpoint: str = ENDPOINT, tz: str = "Europe/Moscow") -> dict:
    return {"endpoint": endpoint, "keys": {"p256dh": "p-key", "auth": "a-key"}, "tz": tz}


@pytest.fixture
async def push_client(postgres_url: str, agent: Agent[GameDeps, str]) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        cookie_secure=False,
        vapid_public_key="public-key-value",
        vapid_private_key=SecretStr("private-key-value"),
        vapid_subject="mailto:ops@example.test",
    )
    async for c in _client(create_app(settings, agent=agent)):
        yield c


async def test_key_is_404_without_vapid_and_served_with_it(
    client: AsyncClient, push_client: AsyncClient
) -> None:
    assert (await client.get(KEY)).status_code == 404
    r = await push_client.get(KEY)
    assert r.status_code == 200 and r.json() == {"public_key": "public-key-value"}


async def test_adult_subscribes_and_the_same_endpoint_stays_one_row(
    push_client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, adult_id, _ = await adult_with_child(push_client)
    for tz in ("Europe/Moscow", "Asia/Tokyo"):
        r = await push_client.post(SUBS, headers=adult, json=sub_body(tz=tz))
        assert r.status_code == 201
    rows = await db_fetch(
        "SELECT member_id, family_id, tz FROM push_subscriptions WHERE family_id = $1", UUID(fid)
    )
    assert [(str(r["member_id"]), str(r["family_id"]), r["tz"]) for r in rows] == [
        (adult_id, fid, "Asia/Tokyo")
    ]


async def test_child_and_anonymous_cannot_manage_subscriptions(
    push_client: AsyncClient, db_fetch
) -> None:
    _, child, fid, *_ = await adult_with_child(push_client)
    assert (await push_client.post(SUBS, headers=child, json=sub_body())).status_code == 403
    assert (
        await push_client.request("DELETE", SUBS, headers=child, json={"endpoint": ENDPOINT})
    ).status_code == 403
    assert (await push_client.post(SUBS, json=sub_body())).status_code == 401
    assert await db_fetch("SELECT 1 FROM push_subscriptions WHERE family_id = $1", UUID(fid)) == []


@pytest.mark.parametrize(
    "body",
    [
        sub_body(endpoint="http://fcm.googleapis.com/x"),
        sub_body(endpoint="https://evil.example/r"),
        sub_body(endpoint="https://evilnotify.windows.com/x"),
        sub_body(endpoint="https://p.test/" + "x" * 2048),
        sub_body(tz="Mars/Olympus"),
        sub_body(tz="../etc/passwd"),
        {**sub_body(), "keys": {"p256dh": "k" * 257, "auth": "a"}},
        {**sub_body(), "keys": {"p256dh": "k", "auth": "a" * 65}},
    ],
)
async def test_bad_subscription_is_refused(push_client: AsyncClient, body: dict, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(push_client)
    assert (await push_client.post(SUBS, headers=adult, json=body)).status_code == 422
    assert await db_fetch("SELECT 1 FROM push_subscriptions WHERE family_id = $1", UUID(fid)) == []


async def test_subscribing_is_404_when_push_is_off(client: AsyncClient) -> None:
    adult, *_ = await adult_with_child(client)
    assert (await client.post(SUBS, headers=adult, json=sub_body())).status_code == 404


async def test_unsubscribe_removes_only_the_own_device(push_client: AsyncClient, db_fetch) -> None:
    adult, *_ = await adult_with_child(push_client)
    other, *_ = await adult_with_child(push_client)
    mine = "https://fcm.googleapis.com/fcm/send/mine"
    other_endpoint = "https://fcm.googleapis.com/fcm/send/other"
    both = "SELECT endpoint FROM push_subscriptions WHERE endpoint = ANY($1)"
    assert (await push_client.post(SUBS, headers=adult, json=sub_body(mine))).status_code == 201
    await push_client.post(SUBS, headers=other, json=sub_body(other_endpoint))
    gone = await push_client.request("DELETE", SUBS, headers=other, json={"endpoint": mine})
    assert gone.status_code == 204
    assert len(await db_fetch(both, [mine, other_endpoint])) == 2  # not theirs: kept
    own = await push_client.request("DELETE", SUBS, headers=adult, json={"endpoint": mine})
    assert own.status_code == 204
    rows = await db_fetch(both, [mine, other_endpoint])
    assert [r["endpoint"] for r in rows] == [other_endpoint]


async def test_opened_records_the_kind_only(push_client: AsyncClient, db_fetch) -> None:
    adult, _, fid, adult_id, _ = await adult_with_child(push_client)
    r = await push_client.post("/api/v1/push/opened", headers=adult, json={"kind": "quest_waiting"})
    assert r.status_code == 204
    rows = await db_fetch(
        "SELECT props, member_id FROM events WHERE kind = 'reminder_opened' AND family_id = $1",
        UUID(fid),
    )
    assert len(rows) == 1 and str(rows[0]["member_id"]) == adult_id
    assert rows[0]["props"] == '{"kind": "quest_waiting", "channel": "push"}'
    bad = await push_client.post("/api/v1/push/opened", headers=adult, json={"kind": "x"})
    assert bad.status_code == 422


async def test_opened_counts_once_per_member_kind_and_day(
    push_client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, *_ = await adult_with_child(push_client)
    opened = "/api/v1/push/opened"
    for kind in ("quest_waiting", "quest_waiting", "chapter_ready", "chapter_ready"):
        assert (
            await push_client.post(opened, headers=adult, json={"kind": kind})
        ).status_code == 204
    rows = await db_fetch(
        "SELECT props FROM events WHERE kind = 'reminder_opened' AND family_id = $1", UUID(fid)
    )
    assert sorted(r["props"] for r in rows) == [
        '{"kind": "chapter_ready", "channel": "push"}',
        '{"kind": "quest_waiting", "channel": "push"}',
    ]


async def test_adventure_poll_is_written_throttled(client: AsyncClient, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    other, *_ = await adult_with_child(client)
    poll = "SELECT last_adventure_poll_at AS at FROM families WHERE id = $1"
    assert (await db_fetch(poll, UUID(fid)))[0]["at"] is None
    assert (await client.get(START.format(fid), headers=other)).status_code == 404
    assert (await db_fetch(poll, UUID(fid)))[0]["at"] is None  # a refused request writes nothing
    await client.get(START.format(fid), headers=adult)
    first = (await db_fetch(poll, UUID(fid)))[0]["at"]
    assert first is not None
    await client.get(START.format(fid), headers=adult)
    assert (await db_fetch(poll, UUID(fid)))[0]["at"] == first  # within 5 s: no second write
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = now() - interval '6 seconds' WHERE id = $1",
        UUID(fid),
    )
    await client.get(START.format(fid), headers=adult)
    assert (await db_fetch(poll, UUID(fid)))[0]["at"] > first


async def test_a_shared_device_moves_to_the_next_adult_of_the_same_family(
    push_client: AsyncClient, db_fetch
) -> None:
    shared = "https://fcm.googleapis.com/fcm/send/shared"
    first, _, fid, first_id, _ = await adult_with_child(push_client)
    r = await push_client.post(f"/api/v1/families/{fid}/members", headers=first, json=ADULT_BODY)
    second_id = r.json()["member"]["id"]
    accepted = await push_client.post(
        "/api/v1/invite/accept", json={"token": r.json()["invite_url"].split("#")[1]}
    )
    second = {"Cookie": f"bumbli_session={accepted.cookies['bumbli_session']}"}
    push_client.cookies.clear()
    assert (await push_client.post(SUBS, headers=first, json=sub_body(shared))).status_code == 201
    r = await push_client.post(SUBS, headers=second, json=sub_body(shared, tz="Asia/Tokyo"))
    assert r.status_code == 201
    rows = await db_fetch(
        "SELECT member_id, tz FROM push_subscriptions WHERE endpoint = $1", shared
    )
    assert [(str(x["member_id"]), x["tz"]) for x in rows] == [(second_id, "Asia/Tokyo")]
    assert first_id != second_id


async def test_another_familys_endpoint_is_refused(push_client: AsyncClient, db_fetch) -> None:
    taken = "https://fcm.googleapis.com/fcm/send/taken"
    owner, _, _, owner_id, _ = await adult_with_child(push_client)
    thief, *_ = await adult_with_child(push_client)
    assert (await push_client.post(SUBS, headers=owner, json=sub_body(taken))).status_code == 201
    r = await push_client.post(SUBS, headers=thief, json=sub_body(taken, tz="Asia/Tokyo"))
    assert r.status_code == 409
    rows = await db_fetch("SELECT member_id, tz FROM push_subscriptions WHERE endpoint = $1", taken)
    assert [(str(x["member_id"]), x["tz"]) for x in rows] == [(owner_id, "Europe/Moscow")]


async def test_resubscribing_keeps_an_active_device_from_eviction(
    push_client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, *_ = await adult_with_child(push_client)
    urls = [f"https://fcm.googleapis.com/fcm/send/r{i}" for i in range(5)]
    for url in urls:
        await push_client.post(SUBS, headers=adult, json=sub_body(url))
    await push_client.post(SUBS, headers=adult, json=sub_body(urls[0]))  # oldest, still in use
    await push_client.post(SUBS, headers=adult, json=sub_body("https://fcm.googleapis.com/f/new"))
    rows = await db_fetch("SELECT endpoint FROM push_subscriptions WHERE family_id = $1", UUID(fid))
    assert urls[0] in {r["endpoint"] for r in rows} and urls[1] not in {r["endpoint"] for r in rows}


async def test_a_member_keeps_at_most_five_devices_the_oldest_goes(
    push_client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, *_ = await adult_with_child(push_client)
    urls = [f"https://fcm.googleapis.com/fcm/send/d{i}" for i in range(7)]
    for url in urls:
        assert (await push_client.post(SUBS, headers=adult, json=sub_body(url))).status_code == 201
    rows = await db_fetch("SELECT endpoint FROM push_subscriptions WHERE family_id = $1", UUID(fid))
    assert sorted(r["endpoint"] for r in rows) == sorted(urls[2:])
