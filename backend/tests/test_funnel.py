import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.cli.funnel import format_report
from app.domain.funnel import EventKind, FunnelStep
from app.repositories.funnel_repository import FunnelRepository
from app.services.funnel_service import FunnelService

WAITLIST = {"email": "Mama@Example.com", "family_size": 4, "kids_age_bands": ["3-5", "6-9"]}
FAMILY = {"title": "Secret Clan", "display_name": "Mama Zoya", "locale": "ru"}


async def _kinds(db_fetch, kind: str) -> list:
    return await db_fetch("SELECT * FROM events WHERE kind = $1", kind)


async def test_waitlist_duplicate_gives_identical_response_and_one_row(client, db_fetch):
    first = await client.post("/api/v1/waitlist", json=WAITLIST)
    again = await client.post("/api/v1/waitlist", json={**WAITLIST, "email": "mama@example.com"})
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    rows = await db_fetch("SELECT email FROM waitlist WHERE email = 'mama@example.com'")
    assert len(rows) == 1


async def test_waitlist_join_event_written_once_without_email(client, db_fetch):
    body = {
        "email": "once@example.com",
        "family_size": 11,
        "kids_age_bands": ["14-17"],
        "locale": "en",
    }
    await client.post("/api/v1/waitlist", json=body)
    await client.post("/api/v1/waitlist", json=body)
    rows = await db_fetch(
        "SELECT props FROM events WHERE kind = 'waitlist_join' AND props = CAST($1 AS jsonb)",
        json.dumps({"family_size": 11, "kids_age_bands": ["14-17"], "locale": "en"}),
    )
    assert len(rows) == 1
    assert "once@example.com" not in rows[0]["props"]


async def test_waitlist_rejects_bad_input(client):
    bad = [
        {**WAITLIST, "email": "not-an-email"},
        {**WAITLIST, "family_size": 13},
        {**WAITLIST, "family_size": 0},
        {**WAITLIST, "kids_age_bands": ["7-8"]},
    ]
    for body in bad:
        assert (await client.post("/api/v1/waitlist", json=body)).status_code == 422


async def test_landing_view_event_is_anonymous_and_restricted(client, db_fetch):
    ok = await client.post("/api/v1/events", json={"kind": "landing_view", "locale": "en"})
    assert ok.status_code == 204
    rows = await _kinds(db_fetch, "landing_view")
    assert rows[-1]["family_id"] is None and rows[-1]["member_id"] is None
    assert json.loads(rows[-1]["props"]) == {"locale": "en"}
    for body in (
        {"kind": "family_created"},
        {"kind": "landing_view", "props": {"x": 1}},
        {"kind": "landing_view", "email": "a@b.co"},
    ):
        assert (await client.post("/api/v1/events", json=body)).status_code == 422


async def test_family_created_event_has_ids_and_no_names(client, db_fetch):
    resp = await client.post("/api/v1/families", json=FAMILY)
    rows = await _kinds(db_fetch, "family_created")
    row = next(r for r in rows if str(r["family_id"]) == resp.json()["family_id"])
    assert str(row["member_id"]) == resp.json()["member"]["id"]
    assert "Secret" not in row["props"] and "Zoya" not in row["props"]


async def test_f1_no_pii_in_any_event_props(client, db_fetch):
    await client.post("/api/v1/waitlist", json={**WAITLIST, "email": "pii@example.com"})
    await client.post("/api/v1/families", json=FAMILY)
    blob = json.dumps([r["props"] for r in await db_fetch("SELECT props FROM events")])
    for secret in ("pii@example.com", "Secret Clan", "Mama Zoya"):
        assert secret not in blob


async def _backdate_first_event(db_fetch, member_id: str, days: int) -> None:
    await db_fetch(
        "UPDATE events SET at = now() - make_interval(days => $2) WHERE member_id = $1::uuid",
        member_id,
        days,
    )


async def _returns(db_fetch, member_id: str) -> list[str]:
    rows = await db_fetch(
        "SELECT kind FROM events WHERE member_id = $1::uuid AND kind LIKE 'return_%' ORDER BY kind",
        member_id,
    )
    return [r["kind"] for r in rows]


async def test_return_d1_written_once(client: AsyncClient, db_fetch):
    member_id = (await client.post("/api/v1/families", json=FAMILY)).json()["member"]["id"]
    await _backdate_first_event(db_fetch, member_id, 1)
    for _ in range(3):
        assert (await client.get("/api/v1/me")).status_code == 200
    assert await _returns(db_fetch, member_id) == ["return_d1"]


async def test_return_d7_and_no_return_on_first_day(client: AsyncClient, db_fetch):
    same = (await client.post("/api/v1/families", json=FAMILY)).json()["member"]["id"]
    await client.get("/api/v1/me")
    assert await _returns(db_fetch, same) == []
    week = (await client.post("/api/v1/families", json=FAMILY)).json()["member"]["id"]
    await _backdate_first_event(db_fetch, week, 7)
    await client.get("/api/v1/me")
    assert await _returns(db_fetch, week) == ["return_d7"]


async def test_funnel_report_counts_and_conversion(postgres_url, client, db_fetch):
    await client.post("/api/v1/events", json={"kind": "landing_view"})
    await client.post("/api/v1/events", json={"kind": "landing_view"})
    await client.post("/api/v1/waitlist", json={**WAITLIST, "email": "rep@example.com"})
    engine = create_async_engine(postgres_url)
    async with engine.connect() as conn:
        steps = {s.kind: s for s in await FunnelRepository(conn).report(days=30)}
    await engine.dispose()
    assert steps[EventKind.LANDING_VIEW].count >= 2
    assert steps[EventKind.WAITLIST_JOIN].count >= 1
    assert steps[EventKind.WORLD_READY].count == 0


def test_cli_format_report_shows_counts_and_conversion():
    steps = [
        FunnelStep(EventKind.LANDING_VIEW, 10, None),
        FunnelStep(EventKind.WAITLIST_JOIN, 2, 0.2),
        FunnelStep(EventKind.WORLD_READY, 0, None),
    ]
    out = format_report(steps, 30)
    assert "landing_view" in out and "20.0%" in out and "last 30 days" in out


async def test_record_event_refuses_personal_props():
    service = FunnelService(AsyncMock(spec=FunnelRepository))
    with pytest.raises(ValueError):
        await service.record_event(EventKind.QUEST_CREATED, props={"email": "x@y.zz"})


async def test_return_d1_survives_a_rolled_back_request(client: AsyncClient, db_fetch):
    other = (await client.post("/api/v1/families", json=FAMILY)).json()["family_id"]
    me = (await client.post("/api/v1/families", json=FAMILY)).json()["member"]["id"]
    await _backdate_first_event(db_fetch, me, 1)
    foreign = await client.get(f"/api/v1/families/{other}/members")
    assert foreign.status_code == 404
    assert (await client.get("/api/v1/me")).status_code == 200
    assert await _returns(db_fetch, me) == ["return_d1"]


async def test_report_returns_count_families_of_the_window_cohort(
    postgres_url, client: AsyncClient, db_fetch
):
    family = (await client.post("/api/v1/families", json=FAMILY)).json()["family_id"]
    engine = create_async_engine(postgres_url)
    async with engine.connect() as conn:
        before = {s.kind: s for s in await FunnelRepository(conn).report(days=30)}
        for _ in range(2):
            await db_fetch(
                "INSERT INTO events (family_id, kind) VALUES ($1::uuid, 'return_d1')", family
            )
        after = {s.kind: s for s in await FunnelRepository(conn).report(days=30)}
    await engine.dispose()
    assert after[EventKind.RETURN_D1].count == before[EventKind.RETURN_D1].count + 1
    assert (after[EventKind.RETURN_D1].conversion or 0) <= 1
