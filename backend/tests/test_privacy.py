from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

NEW_FAMILY = {"title": "Privacy Clan", "display_name": "Papa", "privacy_consent": True}
CHILD = {"display_name": "Kid", "age_band": "6-9", "role": "child"}
ADULT = {"display_name": "Mama", "age_band": "adult", "role": "adult"}


@dataclass
class Person:
    id: str
    family_id: str
    cookie: dict[str, str]


@pytest.fixture
def signup(client: AsyncClient) -> Callable[[str], Awaitable[Person]]:
    async def run(title: str) -> Person:
        resp = await client.post("/api/v1/families", json={**NEW_FAMILY, "title": title})
        assert resp.status_code == 201
        body = resp.json()
        cookie = {"Cookie": f"bumbli_session={resp.cookies['bumbli_session']}"}
        client.cookies.clear()
        return Person(body["member"]["id"], body["family_id"], cookie)

    return run


@pytest.fixture
def invite(
    client: AsyncClient,
) -> Callable[[Person, dict[str, str]], Awaitable[Person]]:
    async def run(owner: Person, body: dict[str, str]) -> Person:
        resp = await client.post(
            f"/api/v1/families/{owner.family_id}/members", json=body, headers=owner.cookie
        )
        data = resp.json()
        token = data["invite_url"].split("#", 1)[1]
        accepted = await client.post("/api/v1/invite/accept", json={"token": token})
        cookie = {"Cookie": f"bumbli_session={accepted.cookies['bumbli_session']}"}
        client.cookies.clear()
        return Person(data["member"]["id"], owner.family_id, cookie)

    return run


@pytest.mark.parametrize("extra", [{}, {"privacy_consent": False}, {"privacy_consent": None}])
async def test_create_without_consent_is_422_and_no_family(client: AsyncClient, db_fetch, extra):
    title = f"NoConsent {uuid4()}"
    body = {"title": title, "display_name": "Papa", **extra}
    resp = await client.post("/api/v1/families", json=body)
    assert resp.status_code == 422
    assert await db_fetch("SELECT 1 FROM families WHERE title = $1", title) == []


async def test_create_with_consent_stores_time_and_version(client: AsyncClient, db_fetch) -> None:
    title = f"Consent {uuid4()}"
    before = datetime.now(UTC)
    resp = await client.post("/api/v1/families", json={**NEW_FAMILY, "title": title})
    assert resp.status_code == 201
    (row,) = await db_fetch(
        "SELECT privacy_consent_at, privacy_policy_version FROM families WHERE id = $1",
        UUID(resp.json()["family_id"]),
    )
    assert row["privacy_policy_version"] == "2026-11-18"
    assert 0 <= (row["privacy_consent_at"] - before).total_seconds() < 30


async def test_me_exposes_is_owner(client: AsyncClient, signup, invite) -> None:
    owner = await signup("Me Clan")
    adult = await invite(owner, ADULT)
    mine = await client.get("/api/v1/me", headers=owner.cookie)
    other = await client.get("/api/v1/me", headers=adult.cookie)
    assert (mine.json()["is_owner"], other.json()["is_owner"]) == (True, False)


async def _seed_personal_rows(db_fetch, owner: Person, child: Person) -> None:
    fam, kid = UUID(owner.family_id), UUID(child.id)
    await db_fetch(
        "INSERT INTO push_subscriptions (member_id, family_id, endpoint, p256dh, auth, tz)"
        " VALUES ($1, $2, $3, 'k', 'a', 'UTC')",
        UUID(owner.id),
        fam,
        f"https://push.example/{uuid4()}",
    )
    await db_fetch(
        "INSERT INTO agent_messages (family_id, member_id, role, channel, content)"
        " VALUES ($1, $2, 'user', 'web', '{}')",
        fam,
        kid,
    )
    await db_fetch("INSERT INTO jobs (kind, family_id) VALUES ('world', $1)", fam)
    # An event the family link has already lost: only the member still identifies it.
    await db_fetch("INSERT INTO events (member_id, kind) VALUES ($1, 'orphan_probe')", kid)
    # A family-level event with no member, as the reminder worker writes them.
    await db_fetch("INSERT INTO events (family_id, kind) VALUES ($1, 'reminder_sent')", fam)
    await db_fetch(
        "INSERT INTO llm_spend (family_id, job_id, attempt, reserved_micro_usd)"
        " VALUES ($1, $2, 1, 10)",
        fam,
        uuid4(),
    )


async def _personal_counts(db_fetch, family_id: str, member_ids: list[str]) -> dict[str, int]:
    fam, members = UUID(family_id), [UUID(m) for m in member_ids]
    queries = {
        "families": ("SELECT count(*) FROM families WHERE id = $1", fam),
        "members": ("SELECT count(*) FROM members WHERE family_id = $1", fam),
        "sessions": ("SELECT count(*) FROM sessions WHERE member_id = ANY($1)", members),
        "push": ("SELECT count(*) FROM push_subscriptions WHERE family_id = $1", fam),
        "messages": ("SELECT count(*) FROM agent_messages WHERE family_id = $1", fam),
        "jobs": ("SELECT count(*) FROM jobs WHERE family_id = $1", fam),
    }
    return {k: (await db_fetch(sql, arg))[0][0] for k, (sql, arg) in queries.items()}


async def test_owner_deletes_family_and_all_personal_rows(
    client: AsyncClient, db_fetch, signup, invite
) -> None:
    owner = await signup("Doomed Clan")
    child = await invite(owner, CHILD)
    await _seed_personal_rows(db_fetch, owner, child)
    spend_before = await db_fetch("SELECT count(*) FROM llm_spend WHERE family_id IS NULL")
    ids = [owner.id, child.id]
    # FKs only null the event's links, so the rows must be tracked by their own ids.
    events = [
        r["id"]
        for r in await db_fetch(
            "SELECT id FROM events WHERE family_id = $1 OR member_id = ANY($2)",
            UUID(owner.family_id),
            [UUID(i) for i in ids],
        )
    ]
    assert len(events) >= 2
    before = await _personal_counts(db_fetch, owner.family_id, ids)
    assert all(n > 0 for n in before.values())

    resp = await client.delete(f"/api/v1/families/{owner.family_id}", headers=owner.cookie)

    assert resp.status_code == 204
    assert resp.content == b""
    assert "bumbli_session=" in resp.headers["set-cookie"]
    assert "Max-Age=0" in resp.headers["set-cookie"]
    assert set((await _personal_counts(db_fetch, owner.family_id, ids)).values()) == {0}
    left = await db_fetch("SELECT count(*) FROM events WHERE id = ANY($1)", events)
    assert left[0][0] == 0
    spend_after = await db_fetch("SELECT count(*) FROM llm_spend WHERE family_id IS NULL")
    assert spend_after[0][0] == spend_before[0][0] + 1


async def test_session_of_deleted_family_is_401(client: AsyncClient, signup, invite) -> None:
    owner = await signup("Gone Clan")
    child = await invite(owner, CHILD)
    await client.delete(f"/api/v1/families/{owner.family_id}", headers=owner.cookie)
    assert (await client.get("/api/v1/me", headers=owner.cookie)).status_code == 401
    assert (await client.get("/api/v1/me", headers=child.cookie)).status_code == 401


async def test_non_owner_cannot_delete(client: AsyncClient, db_fetch, signup, invite) -> None:
    owner = await signup("Kept Clan")
    adult = await invite(owner, ADULT)
    child = await invite(owner, CHILD)
    for who in (adult, child):
        resp = await client.delete(f"/api/v1/families/{owner.family_id}", headers=who.cookie)
        assert resp.status_code == 403
    counts = await _personal_counts(db_fetch, owner.family_id, [owner.id, adult.id, child.id])
    assert counts["families"] == 1
    assert counts["members"] == 3


async def test_foreign_unknown_and_anonymous_delete(client: AsyncClient, db_fetch, signup) -> None:
    mine, theirs = await signup("Mine Clan"), await signup("Theirs Clan")
    foreign = await client.delete(f"/api/v1/families/{theirs.family_id}", headers=mine.cookie)
    unknown = await client.delete(f"/api/v1/families/{uuid4()}", headers=mine.cookie)
    anonymous = await client.delete(f"/api/v1/families/{theirs.family_id}")
    assert (foreign.status_code, unknown.status_code, anonymous.status_code) == (404, 404, 401)
    assert (await _personal_counts(db_fetch, theirs.family_id, [theirs.id]))["families"] == 1
