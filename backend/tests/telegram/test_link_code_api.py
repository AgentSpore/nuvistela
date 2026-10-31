from datetime import UTC, datetime, timedelta

from tests.test_agent_api import make_member

CODE_URL = "/api/v1/families/{}/telegram/link-code"


async def test_adult_gets_short_code_stored_hashed(tg, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    resp = await tg.post(CODE_URL.format(family_id), headers=cookie)
    assert resp.status_code == 200
    body = resp.json()
    assert 6 <= len(body["code"]) <= 10
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=9) < expires - datetime.now(UTC) <= timedelta(minutes=10)
    rows = await db_fetch("SELECT code_hash FROM link_codes")
    assert [r["code_hash"] for r in rows] != [body["code"]] and len(rows) == 1
    assert body["code"] not in rows[0]["code_hash"]


async def test_child_cannot_request_code(tg) -> None:
    cookie, family_id = await make_member(tg)
    add = await tg.post(
        f"/api/v1/families/{family_id}/members",
        headers=cookie,
        json={"display_name": "Kid", "age_band": "6-9", "role": "child"},
    )
    token = add.json()["invite_url"].split("#")[1]
    accepted = await tg.post("/api/v1/invite/accept", json={"token": token})
    child = {"Cookie": f"bumbli_session={accepted.cookies['bumbli_session']}"}
    tg.cookies.clear()
    resp = await tg.post(CODE_URL.format(family_id), headers=child)
    assert resp.status_code == 403


async def test_other_family_id_is_404(tg) -> None:
    cookie_a, _ = await make_member(tg, "A")
    _, family_b = await make_member(tg, "B")
    resp = await tg.post(CODE_URL.format(family_b), headers=cookie_a)
    assert resp.status_code == 404


async def test_no_session_is_401(tg) -> None:
    _, family_id = await make_member(tg)
    assert (await tg.post(CODE_URL.format(family_id))).status_code == 401
