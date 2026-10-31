from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient

ADULT_BODY = {"display_name": "Mama", "age_band": "adult", "role": "adult"}
CHILD_BODY = {"display_name": "Kid", "age_band": "6-9", "role": "child", "interests": ["lego"]}


@dataclass
class Person:
    id: str
    family_id: str
    invite_url: str
    cookie: dict[str, str]


async def _login(client: AsyncClient, invite_url: str) -> dict[str, str]:
    resp = await client.get(invite_url)
    assert resp.status_code == 303
    return {"Cookie": f"bumbli_session={resp.cookies['bumbli_session']}"}


@pytest.fixture
def new_family(client: AsyncClient) -> Callable[[], Awaitable[Person]]:
    async def create() -> Person:
        resp = await client.post(
            "/api/v1/families", json={"title": "Smiths", "display_name": "Papa"}
        )
        assert resp.status_code == 201
        body = resp.json()
        cookie = await _login(client, body["invite_url"])
        return Person(body["member"]["id"], body["family_id"], body["invite_url"], cookie)

    return create


@pytest.fixture
def add_child(client: AsyncClient) -> Callable[[Person], Awaitable[Person]]:
    async def add(adult: Person) -> Person:
        resp = await client.post(
            f"/api/v1/families/{adult.family_id}/members", json=CHILD_BODY, headers=adult.cookie
        )
        assert resp.status_code == 201
        body = resp.json()
        cookie = await _login(client, body["invite_url"])
        return Person(body["member"]["id"], adult.family_id, body["invite_url"], cookie)

    return add


async def test_create_family_then_invite_login(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/families", json={"title": "Smiths", "display_name": "Papa"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["member"]["role"] == "adult"
    assert body["member"]["age_band"] == "adult"

    login = await client.get(body["invite_url"])
    assert login.status_code == 303
    assert login.headers["location"] == "/play"
    set_cookie = login.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["member"]["id"]
    assert "tg_user_id" not in me.json()


async def test_session_cookie_is_secure_when_configured(secure_client: AsyncClient) -> None:
    created = await secure_client.post(
        "/api/v1/families", json={"title": "Smiths", "display_name": "Papa"}
    )
    login = await secure_client.get(created.json()["invite_url"])
    assert "secure" in login.headers["set-cookie"].lower().split("; ")


async def test_creator_has_session_right_after_create(client: AsyncClient) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    set_cookie = created.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"max-age={365 * 24 * 3600}" in set_cookie
    assert created.cookies["bumbli_session"] != created.json()["invite_url"].rsplit("/", 1)[-1]
    added = await client.post(
        f"/api/v1/families/{created.json()['family_id']}/members", json=CHILD_BODY
    )
    assert added.status_code == 201
    assert (await client.get(created.json()["invite_url"])).status_code == 303


async def test_adult_adds_child(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    adult = await new_family()
    resp = await client.post(
        f"/api/v1/families/{adult.family_id}/members", json=CHILD_BODY, headers=adult.cookie
    )
    assert resp.status_code == 201
    assert resp.json()["member"]["interests"] == ["lego"]


async def test_list_members_returns_own_family_without_secrets(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
    add_child: Callable[[Person], Awaitable[Person]],
) -> None:
    adult = await new_family()
    await add_child(adult)
    await add_child(adult)
    resp = await client.get(f"/api/v1/families/{adult.family_id}/members", headers=adult.cookie)
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) == 3
    assert {m["id"] for m in members} >= {adult.id}
    assert all(
        set(m) == {"id", "family_id", "display_name", "age_band", "role", "interests"}
        for m in members
    )


async def test_list_members_other_family_is_404(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    mine, theirs = await new_family(), await new_family()
    resp = await client.get(f"/api/v1/families/{theirs.family_id}/members", headers=mine.cookie)
    unauth = await client.get(
        f"/api/v1/families/{mine.family_id}/members", headers={"Cookie": "bumbli_session=forged"}
    )
    assert (resp.status_code, unauth.status_code) == (404, 401)


async def test_child_cannot_add_member(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
    add_child: Callable[[Person], Awaitable[Person]],
) -> None:
    child = await add_child(await new_family())
    resp = await client.post(
        f"/api/v1/families/{child.family_id}/members", json=ADULT_BODY, headers=child.cookie
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "only adults can add members"}


async def test_child_cannot_reissue_invite(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
    add_child: Callable[[Person], Awaitable[Person]],
) -> None:
    adult = await new_family()
    child = await add_child(adult)
    resp = await client.post(f"/api/v1/members/{adult.id}/invite", headers=child.cookie)
    assert resp.status_code == 403


async def test_other_family_is_invisible(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    mine, theirs = await new_family(), await new_family()
    add = await client.post(
        f"/api/v1/families/{theirs.family_id}/members", json=CHILD_BODY, headers=mine.cookie
    )
    reissue = await client.post(f"/api/v1/members/{theirs.id}/invite", headers=mine.cookie)
    unknown = await client.post(f"/api/v1/members/{uuid4()}/invite", headers=mine.cookie)
    assert (add.status_code, reissue.status_code, unknown.status_code) == (404, 404, 404)


async def test_reissue_kills_session_and_issues_working_invite(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    adult = await new_family()
    resp = await client.post(f"/api/v1/members/{adult.id}/invite", headers=adult.cookie)
    assert resp.status_code == 200

    old = await client.get("/api/v1/me", headers=adult.cookie)
    fresh = await _login(client, resp.json()["invite_url"])
    new = await client.get("/api/v1/me", headers=fresh)
    assert (old.status_code, new.status_code) == (401, 200)


async def test_reissue_kills_unused_old_invite(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
) -> None:
    adult = await new_family()
    added = await client.post(
        f"/api/v1/families/{adult.family_id}/members", json=CHILD_BODY, headers=adult.cookie
    )
    child_id = added.json()["member"]["id"]
    old_invite = added.json()["invite_url"]
    await client.post(f"/api/v1/members/{child_id}/invite", headers=adult.cookie)
    assert (await client.get(old_invite)).status_code == 401


async def test_invite_is_single_use(client: AsyncClient) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    url = created.json()["invite_url"]
    assert (await client.get(url)).status_code == 303
    assert (await client.get(url)).status_code == 401


@pytest.fixture
def db_exec(postgres_url: str) -> Callable[..., Awaitable[None]]:
    async def run(sql: str, *args: str) -> None:
        conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
        try:
            await conn.execute(sql, *args)
        finally:
            await conn.close()

    return run


async def test_expired_invite_is_rejected(
    client: AsyncClient, db_exec: Callable[..., Awaitable[None]]
) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Old"})
    await db_exec(
        "UPDATE members SET invite_expires_at = now() - interval '1 minute' WHERE id = $1::uuid",
        created.json()["member"]["id"],
    )
    assert (await client.get(created.json()["invite_url"])).status_code == 401


async def test_expired_session_is_rejected(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
    db_exec: Callable[..., Awaitable[None]],
) -> None:
    adult = await new_family()
    await db_exec(
        "UPDATE sessions SET expires_at = now() - interval '1 minute' WHERE member_id = $1::uuid",
        adult.id,
    )
    assert (await client.get("/api/v1/me", headers=adult.cookie)).status_code == 401


async def test_cookie_carries_session_not_invite(client: AsyncClient) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    url = created.json()["invite_url"]
    login = await client.get(url)
    assert login.headers["referrer-policy"] == "no-referrer"
    assert login.cookies["bumbli_session"] != url.rsplit("/", 1)[-1]


async def test_invalid_token_is_unauthorized(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/invite/not-a-token")).status_code == 401
    assert (await client.get("/api/v1/me")).status_code == 401
    bad = await client.get("/api/v1/me", headers={"Cookie": "bumbli_session=forged"})
    assert bad.status_code == 401


@pytest.mark.parametrize(
    "patch",
    [
        {"display_name": "x" * 41},
        {"display_name": ""},
        {"interests": ["t"] * 11},
        {"role": "child"},
    ],
)
async def test_member_validation(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]], patch: dict
) -> None:
    adult = await new_family()
    resp = await client.post(
        f"/api/v1/families/{adult.family_id}/members",
        json={**ADULT_BODY, **patch},
        headers=adult.cookie,
    )
    assert resp.status_code == 422
