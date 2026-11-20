import asyncio
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

PATH = "/api/v1/families/{}/world"


def set_worker(client: AsyncClient, running: bool) -> None:
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    app.state.world_worker = True if running else None


@pytest.fixture(autouse=True)
def worker_runs(client: AsyncClient) -> None:
    set_worker(client, True)  # the tests below queue jobs, which needs a worker to exist


async def adult_with_child(c: AsyncClient) -> tuple[dict, dict, str, str, str]:
    r = await c.post(
        "/api/v1/families",
        json={
            "title": "Smiths",
            "display_name": "Anya Smith",
            "interests": ["dinosaurs"],
            "privacy_consent": True,
        },
    )
    fid, adult_id = r.json()["family_id"], r.json()["member"]["id"]
    adult = {"Cookie": f"bumbli_session={r.cookies['bumbli_session']}"}
    c.cookies.clear()
    r = await c.post(
        f"/api/v1/families/{fid}/members",
        headers=adult,
        json={"display_name": "Bobby", "age_band": "6-9", "role": "child", "interests": ["trains"]},
    )
    token = r.json()["invite_url"].split("#")[1]
    r = await c.post("/api/v1/invite/accept", json={"token": token})
    child = {"Cookie": f"bumbli_session={r.cookies['bumbli_session']}"}
    c.cookies.clear()
    return adult, child, fid, adult_id, r.json()["id"]


async def test_only_adult_requests_and_other_family_is_hidden(client: AsyncClient) -> None:
    adult, child, fid, *_ = await adult_with_child(client)
    other, *_ = await adult_with_child(client)
    body = {"genre": "space"}
    assert (await client.post(PATH.format(fid), headers=child, json=body)).status_code == 403
    assert (await client.post(PATH.format(fid), headers=other, json=body)).status_code == 404
    assert (await client.get(PATH.format(fid), headers=other)).status_code == 404
    assert (await client.get(PATH.format(fid), headers=adult)).status_code == 404
    assert (await client.post(PATH.format(fid), headers=adult, json=body)).status_code == 202


async def test_regenerate_is_limited_per_day(client: AsyncClient) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    await client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    codes = []
    for _ in range(4):
        r = await client.post(PATH.format(fid) + "/regenerate", headers=adult)
        codes.append(r.status_code)
    assert codes == [202, 202, 429, 429]


async def test_parallel_requests_cannot_exceed_the_daily_limit(client: AsyncClient) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    results = await asyncio.gather(
        *(client.post(PATH.format(fid), headers=adult, json={"genre": "space"}) for _ in range(6))
    )
    assert sorted(r.status_code for r in results) == [202, 202, 202, 429, 429, 429]


async def test_without_a_world_worker_the_request_is_refused_and_queues_nothing(
    client: AsyncClient, db_fetch
) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    set_worker(client, False)
    for path in (PATH.format(fid), PATH.format(fid) + "/regenerate"):
        r = await client.post(path, headers=adult, json={"genre": "space"})
        assert r.status_code == 409
    assert await db_fetch("SELECT 1 FROM jobs WHERE family_id = $1", UUID(fid)) == []


@pytest.mark.parametrize(("size", "code"), [(300, 202), (301, 422)])
async def test_own_world_description_is_capped_at_300(
    client: AsyncClient, size: int, code: int
) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    body = {"genre": "custom", "custom_genre": "в" * size}
    assert (await client.post(PATH.format(fid), headers=adult, json=body)).status_code == code
