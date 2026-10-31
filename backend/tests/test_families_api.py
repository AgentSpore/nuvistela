from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import pytest
from httpx import AsyncClient

ADULT_BODY = {"display_name": "Mama", "age_band": "adult", "role": "adult"}
CHILD_BODY = {"display_name": "Kid", "age_band": "6-9", "role": "child", "interests": ["lego"]}


@dataclass
class Person:
    id: str
    family_id: str
    cookie: dict[str, str]


def _cookie(invite_url: str) -> dict[str, str]:
    return {"Cookie": f"bumbli_session={invite_url.rsplit('/', 1)[-1]}"}


@pytest.fixture
def new_family(client: AsyncClient) -> Callable[[], Awaitable[Person]]:
    async def create() -> Person:
        resp = await client.post(
            "/api/v1/families", json={"title": "Smiths", "display_name": "Papa"}
        )
        assert resp.status_code == 201
        body = resp.json()
        return Person(body["member"]["id"], body["family_id"], _cookie(body["invite_url"]))

    return create


@pytest.fixture
def add_child(client: AsyncClient) -> Callable[[Person], Awaitable[Person]]:
    async def add(adult: Person) -> Person:
        resp = await client.post(
            f"/api/v1/families/{adult.family_id}/members", json=CHILD_BODY, headers=adult.cookie
        )
        assert resp.status_code == 201
        body = resp.json()
        return Person(body["member"]["id"], adult.family_id, _cookie(body["invite_url"]))

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


async def test_adult_adds_child(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    adult = await new_family()
    resp = await client.post(
        f"/api/v1/families/{adult.family_id}/members", json=CHILD_BODY, headers=adult.cookie
    )
    assert resp.status_code == 201
    assert resp.json()["member"]["interests"] == ["lego"]


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


async def test_reissue_invalidates_old_cookie(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    adult = await new_family()
    resp = await client.post(f"/api/v1/members/{adult.id}/invite", headers=adult.cookie)
    assert resp.status_code == 200

    old = await client.get("/api/v1/me", headers=adult.cookie)
    new = await client.get("/api/v1/me", headers=_cookie(resp.json()["invite_url"]))
    assert (old.status_code, new.status_code) == (401, 200)


async def test_old_invite_link_dies_after_reissue(
    client: AsyncClient, new_family: Callable[[], Awaitable[Person]]
) -> None:
    adult = await new_family()
    old_token = adult.cookie["Cookie"].split("=", 1)[1]
    await client.post(f"/api/v1/members/{adult.id}/invite", headers=adult.cookie)
    assert (await client.get(f"/api/v1/invite/{old_token}")).status_code == 401


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
