from httpx import AsyncClient


async def test_health_ok_with_real_postgres(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


async def test_health_503_when_db_unreachable(client_db_down: AsyncClient) -> None:
    resp = await client_db_down.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "ok", "db": "unavailable"}
