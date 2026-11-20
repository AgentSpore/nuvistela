from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from pydantic_ai import Agent

from app.agent.deps import GameDeps
from app.api.client_ip import client_ip
from app.core.config import Settings
from app.main import create_app
from app.services.admission import DailyCounter, Window, WindowLimiter

FAMILY = {"title": "Smiths", "display_name": "Papa", "privacy_consent": True}
FULL = {"detail": {"code": "daily_full"}}
LIMITED = {"detail": {"code": "rate_limited"}}


def _from(ip: str) -> dict[str, str]:
    return {"X-Forwarded-For": f"{ip}, 10.0.0.2"}


def _request(xff: str | None, peer: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    scope = {"type": "http", "headers": headers, "client": (peer, 1) if peer else None}
    return Request(scope)


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def test_window_limiter_enforces_every_window() -> None:
    clock = Clock()
    limiter = WindowLimiter([Window(3, 3600), Window(5, 86400)], clock)
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("b")
    clock.now = 3601
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]
    clock.now = 86401
    assert limiter.allow("a")


def test_window_limiter_bounds_its_keys_and_evicts_the_oldest() -> None:
    limiter = WindowLimiter([Window(1, 10)], Clock(), max_keys=3)
    for key in "abcdef":
        limiter.allow(key)
    assert limiter.tracked_keys() == 3
    assert not limiter.allow("f")  # the newest keys are still remembered
    assert limiter.allow("a")  # the oldest was evicted and starts afresh


def test_window_limiter_sweeps_idle_keys_at_most_every_interval() -> None:
    clock = Clock()
    limiter = WindowLimiter([Window(1, 10)], clock, sweep_every=60)
    for key in "abc":
        limiter.allow(key)
    clock.now = 11  # idle, but the sweep interval has not passed
    limiter.allow("d")
    assert limiter.tracked_keys() == 4
    clock.now = 61
    limiter.allow("e")
    assert limiter.tracked_keys() == 1


def test_daily_counter_restarts_with_the_utc_day() -> None:
    day = [date(2026, 11, 19)]
    counter = DailyCounter(lambda: day[0])
    counter.add()
    counter.add()
    assert counter.count() == 2
    day[0] = date(2026, 11, 20)
    assert counter.count() == 0


@pytest.mark.parametrize(
    ("xff", "peer", "expected"),
    [
        ("9.9.9.9, 8.8.8.8, 10.0.0.2", "10.0.0.3", "8.8.8.8"),
        ("1.1.1.1, 8.8.8.8", "10.0.0.3", "8.8.8.8"),
        ("8.8.8.8, 172.18.0.4, 192.168.1.1", "10.0.0.3", "8.8.8.8"),
        ("garbage, 2606:4700::1111, fd00::1", "10.0.0.3", "2606:4700::/64"),
        ("::ffff:8.8.8.8", "10.0.0.3", "8.8.8.8"),
        ("2606:4700::aaaa", "10.0.0.3", "2606:4700::/64"),
        ("2606:4700:0:1::1", "10.0.0.3", "2606:4700:0:1::/64"),
        ("10.0.0.2", "10.0.0.3", "10.0.0.3"),
        (None, "8.8.4.4", "8.8.4.4"),
        (None, None, "-"),
    ],
)
def test_client_ip_takes_rightmost_public_address(
    xff: str | None, peer: str | None, expected: str
) -> None:
    assert client_ip(_request(xff, peer)) == expected


async def test_fourth_family_from_one_ip_in_an_hour_is_refused(client: AsyncClient) -> None:
    for _ in range(3):
        assert (
            await client.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.8"))
        ).status_code == 201
    refused = await client.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.8"))
    assert (refused.status_code, refused.json()) == (429, LIMITED)
    other = await client.post("/api/v1/families", json=FAMILY, headers=_from("8.8.4.4"))
    assert other.status_code == 201


async def test_forged_leftmost_forwarded_entry_does_not_bypass(client: AsyncClient) -> None:
    for n in range(3):
        headers = {"X-Forwarded-For": f"5.5.5.{n}, 1.1.1.1, 10.0.0.2"}
        assert (
            await client.post("/api/v1/families", json=FAMILY, headers=headers)
        ).status_code == 201
    headers = {"X-Forwarded-For": "5.5.5.99, 1.1.1.1, 10.0.0.2"}
    refused = await client.post("/api/v1/families", json=FAMILY, headers=headers)
    assert (refused.status_code, refused.json()) == (429, LIMITED)


async def test_thirty_first_invite_accept_from_one_ip_is_refused(client: AsyncClient) -> None:
    codes = [
        (
            await client.post(
                "/api/v1/invite/accept", json={"token": "x" * 20}, headers=_from("9.9.9.9")
            )
        ).status_code
        for _ in range(31)
    ]
    assert codes == [401] * 30 + [429]


async def _today_count(db_fetch) -> int:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await db_fetch("SELECT count(*) AS n FROM families WHERE created_at >= $1", midnight)
    return rows[0]["n"]


async def _app_client(
    url: str, agent: Agent[GameDeps, str], cap: int
) -> AsyncIterator[AsyncClient]:
    settings = Settings(database_url=url, cookie_secure=False, max_new_families_per_day=cap)
    app = create_app(settings, agent=agent)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def test_family_past_the_daily_cap_is_refused(
    postgres_url: str, agent: Agent[GameDeps, str], db_fetch
) -> None:
    cap = await _today_count(db_fetch) + 2
    async for c in _app_client(postgres_url, agent, cap):
        for n in range(2):
            made = await c.post("/api/v1/families", json=FAMILY, headers=_from(f"8.8.8.{n}"))
            assert made.status_code == 201
        refused = await c.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.9"))
        assert (refused.status_code, refused.json()) == (429, FULL)


async def test_zero_cap_means_unlimited(
    postgres_url: str, agent: Agent[GameDeps, str], db_fetch
) -> None:
    async for c in _app_client(postgres_url, agent, 0):
        made = await c.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.1"))
        assert made.status_code == 201


async def test_deleting_a_family_does_not_free_its_daily_place(
    postgres_url: str, agent: Agent[GameDeps, str], db_fetch
) -> None:
    cap = await _today_count(db_fetch) + 1
    async for c in _app_client(postgres_url, agent, cap):
        made = await c.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.1"))
        assert made.status_code == 201
        gone = await c.delete(f"/api/v1/families/{made.json()['family_id']}")
        assert gone.status_code == 204
        again = await c.post("/api/v1/families", json=FAMILY, headers=_from("8.8.8.2"))
        assert (again.status_code, again.json()) == (429, FULL)
