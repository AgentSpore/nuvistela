from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import pytest
from httpx import AsyncClient

from tests.conftest import MIGRATIONS_DIR

ADULT_BODY = {"display_name": "Mama", "age_band": "adult", "role": "adult"}
CHILD_BODY = {"display_name": "Kid", "age_band": "6-9", "role": "child"}


@dataclass
class Person:
    id: str
    family_id: str
    invite_url: str
    cookie: dict[str, str]


@pytest.fixture
def login(client: AsyncClient) -> Callable[[str], Awaitable[dict[str, str]]]:
    async def run(invite_url: str) -> dict[str, str]:
        token = invite_url.split("#", 1)[1]
        resp = await client.post("/api/v1/invite/accept", json={"token": token})
        assert resp.status_code == 200
        return {"Cookie": f"bumbli_session={resp.cookies['bumbli_session']}"}

    return run


@pytest.fixture
async def owner(client: AsyncClient, login: Callable[[str], Awaitable[dict[str, str]]]) -> Person:
    resp = await client.post("/api/v1/families", json={"title": "Smiths", "display_name": "Papa"})
    body = resp.json()
    return Person(
        body["member"]["id"], body["family_id"], body["invite_url"], await login(body["invite_url"])
    )


@pytest.fixture
def add(
    client: AsyncClient, owner: Person, login: Callable[[str], Awaitable[dict[str, str]]]
) -> Callable[[dict[str, str]], Awaitable[Person]]:
    async def run(body: dict[str, str]) -> Person:
        resp = await client.post(
            f"/api/v1/families/{owner.family_id}/members", json=body, headers=owner.cookie
        )
        data = resp.json()
        return Person(
            data["member"]["id"],
            owner.family_id,
            data["invite_url"],
            await login(data["invite_url"]),
        )

    return run


async def _reissue(client: AsyncClient, actor: Person, target: Person) -> int:
    resp = await client.post(f"/api/v1/members/{target.id}/invite", headers=actor.cookie)
    return resp.status_code


async def test_owner_reissues_another_adult(
    client: AsyncClient, owner: Person, add: Callable[[dict[str, str]], Awaitable[Person]]
) -> None:
    mama = await add(ADULT_BODY)
    assert await _reissue(client, owner, mama) == 200


async def test_non_owner_adult_cannot_reissue_another_adult(
    client: AsyncClient, owner: Person, add: Callable[[dict[str, str]], Awaitable[Person]]
) -> None:
    mama = await add(ADULT_BODY)
    assert await _reissue(client, mama, owner) == 403


async def test_non_owner_adult_reissues_child_and_self(
    client: AsyncClient, owner: Person, add: Callable[[dict[str, str]], Awaitable[Person]]
) -> None:
    mama = await add(ADULT_BODY)
    kid = await add(CHILD_BODY)
    assert (await _reissue(client, mama, kid), await _reissue(client, mama, mama)) == (200, 200)


async def test_child_reissues_nothing(
    client: AsyncClient, owner: Person, add: Callable[[dict[str, str]], Awaitable[Person]]
) -> None:
    kid = await add(CHILD_BODY)
    assert (await _reissue(client, kid, owner), await _reissue(client, kid, kid)) == (403, 403)


async def test_cross_family_reissue_is_404(client: AsyncClient, owner: Person) -> None:
    other = await client.post("/api/v1/families", json={"title": "Jones", "display_name": "Bob"})
    stranger = Person(other.json()["member"]["id"], other.json()["family_id"], "", {})
    assert await _reissue(client, owner, stranger) == 404


async def test_is_owner_true_only_for_creator(
    client: AsyncClient, owner: Person, add: Callable[[dict[str, str]], Awaitable[Person]]
) -> None:
    mama = await add(ADULT_BODY)
    await add(CHILD_BODY)
    listed = await client.get(f"/api/v1/families/{owner.family_id}/members", headers=owner.cookie)
    flags = {m["id"]: m["is_owner"] for m in listed.json()}
    me_owner = await client.get("/api/v1/me", headers=owner.cookie)
    me_mama = await client.get("/api/v1/me", headers=mama.cookie)
    assert [i for i, f in flags.items() if f] == [owner.id]
    assert (me_owner.json()["is_owner"], me_mama.json()["is_owner"]) == (True, False)


async def test_migration_backfills_earliest_adult(postgres_url: str) -> None:
    dsn = postgres_url.replace("+asyncpg", "")
    admin = await asyncpg.connect(dsn)
    name = f"k6_{uuid4().hex[:8]}"
    await admin.execute(f"CREATE DATABASE {name}")
    await admin.close()
    conn = await asyncpg.connect(dsn.rsplit("/", 1)[0] + "/" + name)
    try:
        for version in ("V1__init.sql", "V2__spend_store.sql"):
            await conn.execute((MIGRATIONS_DIR / version).read_text())
        fam = await conn.fetchval("INSERT INTO families (title) VALUES ('f') RETURNING id")
        solo = await conn.fetchval("INSERT INTO families (title) VALUES ('kids') RETURNING id")
        rows = [
            ("kid", "6-9", "child", "2024-01-01"),
            ("late", "adult", "adult", "2024-03-01"),
            ("early", "adult", "adult", "2024-02-01"),
        ]
        for n, band, role, at in rows:
            await conn.execute(
                "INSERT INTO members (family_id, display_name, age_band, role, created_at)"
                " VALUES ($1, $2, $3, $4, $5)",
                fam,
                n,
                band,
                role,
                datetime.fromisoformat(at).replace(tzinfo=UTC),
            )
        await conn.execute(
            "INSERT INTO members (family_id, display_name, age_band, role)"
            " VALUES ($1, 'k', '6-9', 'child')",
            solo,
        )
        await conn.execute((MIGRATIONS_DIR / "V3__family_owner.sql").read_text())
        owners = {
            r["title"]: r["name"]
            for r in await conn.fetch(
                "SELECT f.title, m.display_name AS name FROM families f"
                " LEFT JOIN members m ON m.id = f.owner_member_id"
            )
        }
    finally:
        await conn.close()
        admin = await asyncpg.connect(dsn)
        await admin.execute(f"DROP DATABASE {name}")
        await admin.close()
    assert owners == {"f": "early", "kids": None}
