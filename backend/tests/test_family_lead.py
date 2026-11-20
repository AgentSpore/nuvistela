"""POST /families with pilot attribution records one server-side lead for the session."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.repositories.pilot_repository import PilotRepository

FAMILY = {"title": "Smiths", "display_name": "Papa", "privacy_consent": True, "locale": "en"}


def _attribution(source: str) -> dict:
    return {"session_id": str(uuid4()), "source": source, "intent": "family"}


async def test_family_with_attribution_records_one_lead(client, db_fetch):
    attribution = _attribution("telegram")
    response = await client.post("/api/v1/families", json={**FAMILY, "attribution": attribution})
    assert response.status_code == 201
    rows = await db_fetch(
        "SELECT e.kind, e.source, e.locale, e.intent, s.source AS first_touch"
        " FROM pilot_events e JOIN pilot_sessions s USING (session_id)"
        " WHERE session_id = $1::uuid",
        attribution["session_id"],
    )
    assert [dict(row) for row in rows] == [
        {
            "kind": "lead_created",
            "source": "telegram",
            "locale": "en",
            "intent": "family",
            "first_touch": "telegram",
        }
    ]


async def test_family_without_attribution_records_no_lead(client, db_fetch):
    before = await db_fetch("SELECT count(*) AS n FROM pilot_events WHERE kind = 'lead_created'")
    assert (await client.post("/api/v1/families", json=FAMILY)).status_code == 201
    after = await db_fetch("SELECT count(*) AS n FROM pilot_events WHERE kind = 'lead_created'")
    assert after[0]["n"] == before[0]["n"]


@pytest.mark.parametrize(
    "attribution",
    [
        {"session_id": str(uuid4()), "source": "arbitrary"},
        {"session_id": str(uuid4()), "source": "x", "email": "synthetic@example.com"},
    ],
)
async def test_bad_attribution_is_refused_before_a_family_exists(client, db_fetch, attribution):
    title = f"lead-{uuid4().hex[:8]}"
    body = {**FAMILY, "title": title, "attribution": attribution}
    assert (await client.post("/api/v1/families", json=body)).status_code == 422
    rows = await db_fetch("SELECT count(*) AS n FROM families WHERE title = $1", title)
    assert rows[0]["n"] == 0


@pytest.mark.parametrize("source", ["x", "telegram", "substack", "youtube"])
async def test_client_event_accepts_launch_sources(client, db_fetch, source):
    event = {
        "event_id": str(uuid4()),
        "session_id": str(uuid4()),
        "kind": "landing_view",
        "locale": "ru",
        "source": source,
    }
    assert (await client.post("/api/v1/pilot/events", json=event)).status_code == 204
    rows = await db_fetch(
        "SELECT source FROM pilot_sessions WHERE session_id = $1::uuid", event["session_id"]
    )
    assert rows[0]["source"] == source


async def _youtube_leads(postgres_url: str) -> int:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            rows = await PilotRepository(conn).report(30)
    finally:
        await engine.dispose()
    return sum(r["lead"] for r in rows if (r["source"], r["locale"]) == ("youtube", "en"))


async def test_report_breaks_family_leads_down_by_launch_source(client, postgres_url):
    before = await _youtube_leads(postgres_url)
    attribution = _attribution("youtube")
    landing = {**attribution, "event_id": str(uuid4()), "kind": "landing_view", "locale": "en"}
    assert (await client.post("/api/v1/pilot/events", json=landing)).status_code == 204
    body = {**FAMILY, "attribution": attribution}
    assert (await client.post("/api/v1/families", json=body)).status_code == 201
    assert await _youtube_leads(postgres_url) == before + 1


async def test_failed_lead_write_keeps_the_new_family(client, db_fetch, monkeypatch):
    async def broken_add(self, event, enforce_cap=False):
        await self._conn.execute(text("SELECT 1 / 0"))  # a real error that aborts the statement

    monkeypatch.setattr(PilotRepository, "add", broken_add)
    title = f"lead-{uuid4().hex[:8]}"
    body = {**FAMILY, "title": title, "attribution": _attribution("x")}
    assert (await client.post("/api/v1/families", json=body)).status_code == 201
    rows = await db_fetch("SELECT count(*) AS n FROM families WHERE title = $1", title)
    assert rows[0]["n"] == 1


async def _share_leads(postgres_url: str) -> int:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            return (await PilotRepository(conn).share_funnel(30))["leads"]
    finally:
        await engine.dispose()


async def test_share_funnel_counts_a_session_with_two_games_once(client, postgres_url):
    before = await _share_leads(postgres_url)
    body = {**FAMILY, "attribution": _attribution("share")}
    for _ in range(2):
        assert (await client.post("/api/v1/families", json=body)).status_code == 201
    assert await _share_leads(postgres_url) == before + 1
