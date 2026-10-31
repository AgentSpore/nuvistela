import asyncpg
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


class SeenAtResponseStart:
    """ASGI wrapper: when the response starts, count the member on a fresh connection."""

    def __init__(self, app, pg_url: str, name: str) -> None:
        self._app, self._pg_url, self._name = app, pg_url, name
        self.visible: int | None = None

    async def __call__(self, scope, receive, send) -> None:
        async def watching_send(message) -> None:
            if message["type"] == "http.response.start" and self.visible is None:
                conn = await asyncpg.connect(self._pg_url.replace("+asyncpg", ""))
                try:
                    self.visible = await conn.fetchval(
                        "SELECT count(*) FROM members WHERE display_name = $1", self._name
                    )
                finally:
                    await conn.close()
            await send(message)

        await self._app(scope, receive, watching_send)


async def test_family_is_committed_before_response_starts(postgres_url: str) -> None:
    app = create_app(Settings(database_url=postgres_url, cookie_secure=False))
    observer = SeenAtResponseStart(app, postgres_url, "CommitProbe")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=observer), base_url="http://t") as c:
            resp = await c.post(
                "/api/v1/families", json={"title": "T", "display_name": "CommitProbe"}
            )
    assert resp.status_code == 201
    assert observer.visible == 1
