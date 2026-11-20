import asyncio
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.cli.pilot import format_report, format_share_funnel
from app.repositories.pilot_repository import PilotRepository


@pytest.fixture
def event():
    return {
        "event_id": str(uuid4()),
        "session_id": str(uuid4()),
        "kind": "landing_view",
        "locale": "es",
        "source": "community",
        "intent": None,
    }


async def test_pilot_retries_are_idempotent_and_first_touch_is_immutable(client, db_fetch, event):
    responses = await asyncio.gather(
        *(client.post("/api/v1/pilot/events", json=event) for _ in range(4))
    )
    assert [response.status_code for response in responses] == [204] * 4
    rows = await db_fetch(
        "SELECT count(*) FROM pilot_events WHERE event_id = $1::uuid", event["event_id"]
    )
    assert rows[0]["count"] == 1
    later = {
        **event,
        "event_id": str(uuid4()),
        "kind": "cta_click",
        "locale": "en",
        "source": "share",
        "intent": "solo",
    }
    assert (await client.post("/api/v1/pilot/events", json=later)).status_code == 204
    rows = await db_fetch(
        "SELECT source, locale FROM pilot_sessions WHERE session_id = $1::uuid", event["session_id"]
    )
    assert dict(rows[0]) == {"source": "community", "locale": "es"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "share"),
        ("locale", "en"),
        ("kind", "demo_start"),
        ("intent", "solo"),
        ("session_id", str(uuid4())),
    ],
)
async def test_event_id_conflict_checks_entire_payload(client, event, field, value):
    assert (await client.post("/api/v1/pilot/events", json=event)).status_code == 204
    response = await client.post("/api/v1/pilot/events", json={**event, field: value})
    assert response.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "lead_created"},
        {"source": "arbitrary"},
        {"intent": "other"},
        {"locale": "fr"},
        {"email": "synthetic@example.com"},
        {"props": {}},
        {"session_id": "invalid"},
        {"event_id": "invalid"},
    ],
)
async def test_pilot_rejects_untrusted_payload(client, event, change):
    assert (await client.post("/api/v1/pilot/events", json={**event, **change})).status_code == 422


async def test_waitlist_creates_only_one_server_lead(client, db_fetch, event):
    body = {
        "email": f"pilot-{uuid4().hex}@example.com",
        "family_size": 1,
        "locale": "es",
        "attribution": {"session_id": event["session_id"], "source": "share", "intent": "solo"},
    }
    responses = await asyncio.gather(
        *(client.post("/api/v1/waitlist", json=body) for _ in range(3))
    )
    assert [r.status_code for r in responses] == [200] * 3
    rows = await db_fetch(
        "SELECT kind, intent FROM pilot_events WHERE session_id = $1::uuid", event["session_id"]
    )
    assert [dict(row) for row in rows] == [{"kind": "lead_created", "intent": "solo"}]


async def test_conflicting_concurrent_event_rolls_back_new_session(client, db_fetch, event):
    other = {**event, "session_id": str(uuid4()), "source": "share"}
    responses = await asyncio.gather(
        *(client.post("/api/v1/pilot/events", json=payload) for payload in (event, other))
    )
    assert sorted(r.status_code for r in responses) == [204, 409]
    rows = await db_fetch(
        "SELECT count(*) FROM pilot_sessions WHERE session_id IN ($1::uuid, $2::uuid)",
        event["session_id"],
        other["session_id"],
    )
    assert rows[0]["count"] == 1


async def test_lead_failure_rolls_back_waitlist_and_both_event_tables(client, db_fetch, event):
    session = event["session_id"]
    await db_fetch(
        f"ALTER TABLE pilot_events ADD CONSTRAINT pilot_test_reject "
        f"CHECK (session_id <> '{session}'::uuid) NOT VALID"
    )
    body = {
        "email": f"rollback-{uuid4().hex}@example.com",
        "family_size": 1,
        "locale": "es",
        "attribution": {"session_id": session, "source": "share", "intent": "solo"},
    }
    before = await db_fetch("SELECT count(*) FROM events WHERE kind = 'waitlist_join'")
    try:
        with pytest.raises(IntegrityError):
            await client.post("/api/v1/waitlist", json=body)
        rows = await db_fetch("SELECT count(*) FROM waitlist WHERE email = $1", body["email"])
        assert rows[0]["count"] == 0
        rows = await db_fetch(
            "SELECT count(*) FROM pilot_sessions WHERE session_id = $1::uuid", session
        )
        assert rows[0]["count"] == 0
        after = await db_fetch("SELECT count(*) FROM events WHERE kind = 'waitlist_join'")
        assert after[0]["count"] == before[0]["count"]
    finally:
        await db_fetch("ALTER TABLE pilot_events DROP CONSTRAINT pilot_test_reject")


async def test_report_uses_receipt_cohort_and_exposes_missing_unordered_events(
    client, db_fetch, postgres_url
):
    sessions = [str(uuid4()) for _ in range(4)]
    stages = [
        ["landing_view", "demo_start", "demo_complete", "cta_click", "share_click", "share_click"],
        ["demo_complete"],
        ["cta_click", "landing_view"],
        ["landing_view"],
    ]
    for session, kinds in zip(sessions, stages, strict=True):
        for kind in kinds:
            response = await client.post(
                "/api/v1/pilot/events",
                json={
                    "event_id": str(uuid4()),
                    "session_id": session,
                    "kind": kind,
                    "locale": "zh-CN",
                    "source": "newsletter",
                    "intent": "solo",
                },
            )
            assert response.status_code == 204
    await db_fetch(
        "UPDATE pilot_sessions SET created_at = now() - interval '31 days' "
        "WHERE session_id = $1::uuid",
        sessions[3],
    )
    assert (
        await client.post(
            "/api/v1/waitlist",
            json={
                "email": f"report-{uuid4().hex}@example.com",
                "family_size": 1,
                "locale": "zh-CN",
                "attribution": {
                    "session_id": sessions[0],
                    "source": "newsletter",
                    "intent": "solo",
                },
            },
        )
    ).status_code == 200
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            rows = await PilotRepository(conn).report(30)
    finally:
        await engine.dispose()
    row = next(row for row in rows if row["source"] == "newsletter" and row["locale"] == "zh-CN")
    assert row == {
        "source": "newsletter",
        "locale": "zh-CN",
        "sessions": 3,
        "landing": 2,
        "missing_landing": 1,
        "demo_start": 1,
        "demo_complete": 1,
        "cta": 2,
        "share": 1,
        "lead": 1,
        "solo": 3,
        "family": 0,
        "unordered": 2,
    }
    report = format_report([row], 30)
    assert "first server receipt" in report and "50.0%" in report
    assert "stages need not occur in order" in report


async def test_pilot_migration_repeat_and_columns_exclude_personal_data(db_fetch, postgres_url):
    migration = Path(__file__).resolve().parents[2] / "db/migrations/V7__pilot_attribution.sql"
    connection = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    try:
        await connection.execute(migration.read_text())
    finally:
        await connection.close()
    rows = await db_fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'pilot_events'"
    )
    assert {row["column_name"] for row in rows} == {
        "event_id",
        "session_id",
        "at",
        "kind",
        "locale",
        "source",
        "intent",
    }


def _post(client, event, **change):
    return client.post("/api/v1/pilot/events", json={**event, "event_id": str(uuid4()), **change})


async def _sessions(postgres_url, source, locale, **kwargs):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            rows = await PilotRepository(conn).report(30, **kwargs)
    finally:
        await engine.dispose()
    return sum(r["sessions"] for r in rows if (r["source"], r["locale"]) == (source, locale))


async def test_report_excludes_internal_sessions_unless_asked(client, postgres_url, event):
    event = {**event, "source": "newsletter", "locale": "en"}
    before = await _sessions(postgres_url, "newsletter", "en")
    before_all = await _sessions(postgres_url, "newsletter", "en", include_internal=True)
    internal = {**event, "session_id": str(uuid4()), "internal": True}
    assert (await _post(client, internal)).status_code == 204
    assert (await _post(client, event)).status_code == 204
    assert await _sessions(postgres_url, "newsletter", "en") == before + 1
    assert (
        await _sessions(postgres_url, "newsletter", "en", include_internal=True) == before_all + 2
    )


async def test_internal_flag_reaches_the_server_lead_session(client, db_fetch, event):
    body = {
        "email": f"internal-{uuid4().hex}@example.com",
        "family_size": 1,
        "attribution": {
            "session_id": event["session_id"],
            "source": "direct",
            "internal": True,
        },
    }
    assert (await client.post("/api/v1/waitlist", json=body)).status_code == 200
    rows = await db_fetch(
        "SELECT internal FROM pilot_sessions WHERE session_id = $1::uuid", event["session_id"]
    )
    assert rows[0]["internal"] is True


async def test_session_event_cap_returns_429_without_insert(client, db_fetch, event):
    for _ in range(59):
        assert (await _post(client, event)).status_code == 204
    assert (await client.post("/api/v1/pilot/events", json=event)).status_code == 204
    assert (await _post(client, event)).status_code == 429
    rows = await db_fetch(
        "SELECT count(*) FROM pilot_events WHERE session_id = $1::uuid", event["session_id"]
    )
    assert rows[0]["count"] == 60
    assert (await client.post("/api/v1/pilot/events", json=event)).status_code == 204


async def test_parallel_posts_at_the_cap_accept_exactly_one(client, db_fetch, event):
    for _ in range(59):
        assert (await _post(client, event)).status_code == 204
    responses = await asyncio.gather(*(_post(client, event) for _ in range(30)))
    assert sorted(r.status_code for r in responses) == [204] + [429] * 29
    rows = await db_fetch(
        "SELECT count(*) FROM pilot_events WHERE session_id = $1::uuid", event["session_id"]
    )
    assert rows[0]["count"] == 60


async def test_lead_without_cta_click_is_not_unordered(client, postgres_url, event):
    event = {**event, "source": "share", "locale": "ru"}
    for kind in ("landing_view",):
        assert (await _post(client, event, kind=kind)).status_code == 204
    body = {
        "email": f"nocta-{uuid4().hex}@example.com",
        "family_size": 1,
        "attribution": {"session_id": event["session_id"], "source": "share"},
    }
    assert (await client.post("/api/v1/waitlist", json=body)).status_code == 200
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            rows = await PilotRepository(conn).report(30)
    finally:
        await engine.dispose()
    row = next(r for r in rows if (r["source"], r["locale"]) == ("share", "ru"))
    assert row["lead"] >= 1 and row["unordered"] == 0


async def test_event_cap_check_waits_for_the_session_lock(client, postgres_url, event):
    locker = await asyncpg.connect(postgres_url.replace("+asyncpg", ""))
    tx = locker.transaction()
    await tx.start()
    try:
        await locker.execute("SELECT pg_advisory_xact_lock(hashtext($1))", event["session_id"])
        pending = asyncio.create_task(_post(client, event))
        await asyncio.sleep(0.7)
        assert not pending.done()
    finally:
        await tx.commit()
        await locker.close()
    assert (await pending).status_code == 204


@pytest.mark.parametrize("kind", ["share_viewed", "share_cta"])
async def test_share_page_beacons_are_accepted_from_clients(client, db_fetch, event, kind):
    response = await client.post("/api/v1/pilot/events", json={**event, "kind": kind})
    assert response.status_code == 204
    rows = await db_fetch(
        "SELECT kind FROM pilot_events WHERE event_id = $1::uuid", event["event_id"]
    )
    assert [r["kind"] for r in rows] == [kind]


@pytest.mark.parametrize("kind", ["share_created", "share_revoked"])
async def test_server_only_share_kinds_are_refused_from_clients(client, event, kind):
    assert (
        await client.post("/api/v1/pilot/events", json={**event, "kind": kind})
    ).status_code == 422


async def test_share_funnel_counts_events_in_the_window(client, db_fetch, postgres_url):
    async def count() -> dict[str, int]:
        engine = create_async_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                return await PilotRepository(conn).share_funnel(30)
        finally:
            await engine.dispose()

    before = await count()
    session = str(uuid4())

    async def post(kind: str, session_id: str, internal: bool = False) -> None:
        body = {
            "event_id": str(uuid4()),
            "session_id": session_id,
            "kind": kind,
            "locale": "ru",
            "source": "share",
            "intent": None,
            "internal": internal,
        }
        assert (await client.post("/api/v1/pilot/events", json=body)).status_code == 204

    for kind in ("share_viewed", "share_viewed", "share_cta", "share_cta"):
        await post(kind, session)  # repeats in one session count once
    await post("share_viewed", str(uuid4()))
    await post("share_viewed", str(uuid4()), internal=True)  # own checks are left out
    await db_fetch(
        "INSERT INTO pilot_events (event_id, kind, source)"
        " VALUES (gen_random_uuid(), 'share_created', 'share'),"
        " (gen_random_uuid(), 'share_created', 'share')"
    )
    await db_fetch(
        "INSERT INTO pilot_events (event_id, kind, source, at)"
        " VALUES (gen_random_uuid(), 'share_created', 'share', now() - interval '31 days')"
    )
    lead = {"session_id": session, "source": "share", "intent": None}
    body = {"email": f"f-{uuid4().hex}@example.com", "family_size": 1, "locale": "ru"}
    assert (
        await client.post("/api/v1/waitlist", json={**body, "attribution": lead})
    ).status_code == 200
    direct = {**lead, "session_id": str(uuid4()), "source": "direct"}
    body["email"] = f"d-{uuid4().hex}@example.com"
    assert (
        await client.post("/api/v1/waitlist", json={**body, "attribution": direct})
    ).status_code == 200
    after = await count()
    assert {k: after[k] - before[k] for k in after} == {
        "created": 2,
        "viewed": 2,
        "cta": 1,
        "leads": 1,
    }


def test_funnel_text_is_plain_counts():
    text = format_share_funnel({"created": 3, "viewed": 2, "cta": 1, "leads": 0}, 7)
    assert "last 7 days" in text
    assert text.splitlines()[1:] == [
        "created 3 (links made)",
        "viewed 2 (sessions)",
        "cta 1 (sessions)",
        "new_leads 0 (lead with source=share, internal excluded)",
    ]


async def test_viewer_only_sessions_do_not_enter_the_cohort_report(client, postgres_url):
    async def cohort() -> dict | None:
        engine = create_async_engine(postgres_url)
        try:
            async with engine.connect() as conn:
                rows = await PilotRepository(conn).report(30)
        finally:
            await engine.dispose()
        return next((r for r in rows if r["source"] == "share" and r["locale"] == "ru"), None)

    before = await cohort()
    body = {
        "event_id": str(uuid4()),
        "session_id": str(uuid4()),
        "kind": "share_viewed",
        "locale": "ru",
        "source": "share",
        "intent": None,
    }
    assert (await client.post("/api/v1/pilot/events", json=body)).status_code == 204
    assert await cohort() == before


async def test_session_less_events_must_be_server_share_events(db_fetch):
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await db_fetch(
            "INSERT INTO pilot_events (event_id, kind, source)"
            " VALUES (gen_random_uuid(), 'landing_view', 'direct')"
        )
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await db_fetch(
            "INSERT INTO pilot_events (event_id, session_id, kind, source)"
            " VALUES (gen_random_uuid(), NULL, 'share_viewed', 'share')"
        )
