import time

from httpx import AsyncClient


async def test_health_ok_with_real_postgres(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "agent": "ready"}


async def test_health_503_when_db_unreachable(client_db_down: AsyncClient) -> None:
    resp = await client_db_down.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "db": "unavailable", "agent": "ready"}


async def test_health_answers_within_2s_when_db_blackholed(
    client_db_blackholed: AsyncClient,
) -> None:
    started = time.monotonic()
    resp = await client_db_blackholed.get("/health")
    elapsed = time.monotonic() - started
    assert resp.status_code == 503
    assert elapsed < 2
