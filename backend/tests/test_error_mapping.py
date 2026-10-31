from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.errors import register_error_handlers
from app.domain.errors import Forbidden


class ChildOnly(Forbidden):
    pass


async def test_subclass_of_domain_error_keeps_parent_status() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ChildOnly("children only")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/boom")
    assert (resp.status_code, resp.json()) == (403, {"detail": "children only"})
