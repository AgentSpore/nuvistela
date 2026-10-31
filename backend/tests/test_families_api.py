import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient, Response

ADULT_BODY = {"display_name": "Mama", "age_band": "adult", "role": "adult"}
CHILD_BODY = {"display_name": "Kid", "age_band": "6-9", "role": "child", "interests": ["lego"]}


@dataclass
class Person:
    id: str
    family_id: str
    invite_url: str
    cookie: dict[str, str]


def _token(invite_url: str) -> str:
    assert invite_url.endswith("/join#" + invite_url.split("#", 1)[1])
    return invite_url.split("#", 1)[1]


async def _accept(client: AsyncClient, invite_url: str) -> Response:
    return await client.post("/api/v1/invite/accept", json={"token": _token(invite_url)})


async def _login(client: AsyncClient, invite_url: str) -> dict[str, str]:
    resp = await _accept(client, invite_url)
    assert resp.status_code == 200
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

    login = await _accept(client, body["invite_url"])
    assert login.status_code == 200
    assert login.json()["id"] == body["member"]["id"]
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
    login = await _accept(secure_client, created.json()["invite_url"])
    assert "secure" in login.headers["set-cookie"].lower().split("; ")


async def test_creator_has_session_right_after_create(client: AsyncClient) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    set_cookie = created.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"max-age={365 * 24 * 3600}" in set_cookie
    assert created.cookies["bumbli_session"] != _token(created.json()["invite_url"])
    added = await client.post(
        f"/api/v1/families/{created.json()['family_id']}/members", json=CHILD_BODY
    )
    assert added.status_code == 201
    assert (await _accept(client, created.json()["invite_url"])).status_code == 200


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
    assert (await _accept(client, old_invite)).status_code == 401


async def test_invite_is_single_use(client: AsyncClient) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    url = created.json()["invite_url"]
    assert (await _accept(client, url)).status_code == 200
    assert (await _accept(client, url)).status_code == 401


@pytest.fixture
def db_value(postgres_url: str) -> Callable[..., Awaitable[Any]]:
    async def run(sql: str, *args: str) -> Any:
        conn = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
        try:
            return await conn.fetchval(sql, *args)
        finally:
            await conn.close()

    return run


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
    assert (await _accept(client, created.json()["invite_url"])).status_code == 401


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
    login = await _accept(client, url)
    assert login.headers["referrer-policy"] == "no-referrer"
    assert login.cookies["bumbli_session"] != _token(url)


async def test_invalid_token_is_unauthorized(client: AsyncClient) -> None:
    bad_invite = await client.post("/api/v1/invite/accept", json={"token": "not-a-token"})
    assert bad_invite.status_code == 401
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


async def test_get_cannot_consume_invite(client: AsyncClient) -> None:
    """A link-preview crawler only issues GET; it must not burn the invite."""
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    url = created.json()["invite_url"]
    token = _token(url)
    for path in (f"/api/v1/invite/{token}", f"/join/{token}", "/join"):
        resp = await client.get(path)
        assert resp.status_code in (404, 405)
        assert "bumbli_session=" not in resp.headers.get("set-cookie", "")
    assert (await _accept(client, url)).status_code == 200


async def test_concurrent_accepts_yield_one_session(
    client: AsyncClient, db_value: Callable[..., Awaitable[Any]]
) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Race"})
    url = created.json()["invite_url"]
    member_id = created.json()["member"]["id"]
    before = await db_value("SELECT count(*) FROM sessions WHERE member_id = $1::uuid", member_id)
    results = await asyncio.gather(*(_accept(client, url) for _ in range(8)))
    after = await db_value("SELECT count(*) FROM sessions WHERE member_id = $1::uuid", member_id)
    assert sorted(r.status_code for r in results) == [200] + [401] * 7
    assert after - before == 1


async def test_adult_cannot_reissue_another_adults_invite(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    papa = await new_family()
    added = await client.post(
        f"/api/v1/families/{papa.family_id}/members", json=ADULT_BODY, headers=papa.cookie
    )
    mama_id = added.json()["member"]["id"]
    resp = await client.post(f"/api/v1/members/{mama_id}/invite", headers=papa.cookie)
    assert resp.status_code == 403
    assert (await _accept(client, added.json()["invite_url"])).status_code == 200


async def test_adult_can_reissue_a_childs_invite(
    client: AsyncClient,
    new_family: Callable[[], Awaitable[Person]],
    add_child: Callable[[Person], Awaitable[Person]],
) -> None:
    papa = await new_family()
    kid = await add_child(papa)
    resp = await client.post(f"/api/v1/members/{kid.id}/invite", headers=papa.cookie)
    assert resp.status_code == 200


async def test_login_purges_members_expired_sessions(
    client: AsyncClient,
    db_exec: Callable[..., Awaitable[None]],
    db_value: Callable[..., Awaitable[Any]],
) -> None:
    created = await client.post("/api/v1/families", json={"title": "T", "display_name": "Papa"})
    member_id = created.json()["member"]["id"]
    await db_exec(
        "UPDATE sessions SET expires_at = now() - interval '1 day' WHERE member_id = $1::uuid",
        member_id,
    )
    assert (await _accept(client, created.json()["invite_url"])).status_code == 200
    rows = await db_value("SELECT count(*) FROM sessions WHERE member_id = $1::uuid", member_id)
    assert rows == 1


@pytest.mark.parametrize(("locale", "prefix"), [("ru", "/join#"), ("en", "/en/join#")])
async def test_invite_url_carries_family_locale_prefix(
    client: AsyncClient, locale: str, prefix: str
) -> None:
    created = await client.post(
        "/api/v1/families", json={"title": "T", "display_name": "Papa", "locale": locale}
    )
    assert created.json()["invite_url"].startswith(prefix)
    cookie = await _login(client, created.json()["invite_url"])
    family_id = created.json()["family_id"]
    added = await client.post(
        f"/api/v1/families/{family_id}/members", json=CHILD_BODY, headers=cookie
    )
    assert added.json()["invite_url"].startswith(prefix)
    child_id = added.json()["member"]["id"]
    again = await client.post(f"/api/v1/members/{child_id}/invite", headers=cookie)
    assert again.json()["invite_url"].startswith(prefix)
