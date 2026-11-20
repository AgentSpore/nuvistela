import asyncio
import base64
import io
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent.image_client import OpenRouterImageClient
from app.agent.world_generator import build_world_generator
from app.core.config import Settings
from app.main import _start_image_worker, _stop_worker, create_app
from app.workers.image_worker import ImageWorker
from app.workers.world_worker import WorldWorker
from tests.conftest import _client
from tests.test_world import world_args
from tests.test_world_api import PATH, adult_with_child

COST = 0.0336


def picture() -> str:
    out = io.BytesIO()
    Image.new("RGB", (1264, 848), (30, 90, 160)).save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def settings(url: str, **extra: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": url,
        "cookie_secure": False,
        "world_worker_enabled": False,
        "world_retry_delay_s": 0,
        "world_model": "vendor/world-x",
        "image_model": "vendor/img",
        "openrouter_api_key": SecretStr("k"),
        **extra,
    }
    return Settings(**values)


@dataclass
class Env:
    app: FastAPI
    client: AsyncClient
    world: WorldWorker
    image: ImageWorker
    db_fetch: Callable[..., Awaitable[list]]
    client_for_images: OpenRouterImageClient
    requests: list[dict] = field(default_factory=list)
    reserved_at_call: list[list] = field(default_factory=list)
    http_status: list[int] = field(default_factory=list)  # next answers; empty = success
    world_fails: list[bool] = field(default_factory=list)
    cost: list[float] = field(default_factory=lambda: [COST])

    async def new_family_world(self, drain_world: bool = True) -> str:
        adult, _, fid, *_ = await adult_with_child(self.client)
        self.adult = adult
        await self.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
        if drain_world:
            while await self.world.run_once():
                pass
        return fid

    async def drain_images(self) -> int:
        n = 0
        while await self.image.run_once():
            n += 1
        return n

    async def jobs(self, kind: str) -> list:
        return await self.db_fetch("SELECT * FROM jobs WHERE kind = $1", kind)

    async def spend(self) -> list:
        return await self.db_fetch(
            "SELECT * FROM llm_spend WHERE kind = 'image' ORDER BY created_at"
        )


async def build(postgres_url: str, agent, db_fetch, **extra: Any) -> AsyncIterator[Env]:
    await db_fetch("DELETE FROM jobs")
    await db_fetch("DELETE FROM llm_spend")
    cfg = settings(postgres_url, **extra)
    gen = build_world_generator(cfg)
    state: dict = {}

    async def script(messages, info) -> ModelResponse:
        if state["env"].world_fails and state["env"].world_fails.pop(0):
            raise ModelAPIError("m", "boom")
        ids = re.findall(
            r'member_id\\+": \\+"([0-9a-f-]{36})', json.dumps([str(m) for m in messages])
        )
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, world_args(ids))])

    async def handler(request: httpx2.Request) -> httpx2.Response:
        env: Env = state["env"]
        env.requests.append(json.loads(request.content))
        env.reserved_at_call.append(
            await db_fetch("SELECT state, actual_micro_usd FROM llm_spend WHERE kind = 'image'")
        )
        if env.http_status and (status := env.http_status.pop(0)) != 200:
            return httpx2.Response(status, json={})
        body = {
            "choices": [{"message": {"images": [{"image_url": {"url": picture()}}]}}],
            "usage": {"cost": env.cost[0]},
        }
        return httpx2.Response(200, json=body)

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    client_ = OpenRouterImageClient(settings(postgres_url), http_client=http)
    app = create_app(cfg, agent=agent, world_generator=gen)
    with gen.agent.override(model=FunctionModel(script)):
        async for c in _client(app):
            app.state.world_worker = True
            worker_cfg = settings(postgres_url, **extra)
            env = Env(
                app, c, WorldWorker(app.state.engine, gen, cfg),
                ImageWorker(app.state.engine, client_, worker_cfg), db_fetch, client_,
            )  # fmt: skip
            state["env"] = env
            yield env


@pytest.fixture
async def env(postgres_url: str, agent, db_fetch) -> AsyncIterator[Env]:
    async for e in build(postgres_url, agent, db_fetch):
        yield e


@pytest.fixture
async def model_off(postgres_url: str, agent, db_fetch) -> AsyncIterator[Env]:
    async for e in build(postgres_url, agent, db_fetch, image_model=""):
        yield e


async def cover_row(env: Env, fid: str):
    rows = await env.db_fetch("SELECT * FROM world_images WHERE family_id = $1", UUID(fid))
    return rows[0] if rows else None


async def test_ready_world_enqueues_exactly_one_image_job(env: Env) -> None:
    fid = await env.new_family_world()
    jobs = await env.jobs("image")
    assert len(jobs) == 1
    assert json.loads(jobs[0]["payload"]).keys() == {"world_job_id"}
    row = await cover_row(env, fid)
    assert row["status"] == "pending"
    assert env.requests == []  # enqueueing buys nothing


async def test_fallback_world_has_no_job_and_no_purchase(env: Env) -> None:
    env.world_fails[:] = [True, True, True]
    fid = await env.new_family_world()
    status = (await env.client.get(PATH.format(fid), headers=env.adult)).json()["status"]
    assert status == "fallback"
    assert await env.jobs("image") == []
    assert await cover_row(env, fid) is None
    assert await env.drain_images() == 0


async def test_model_off_enqueues_nothing(model_off: Env) -> None:
    fid = await model_off.new_family_world()
    assert await model_off.jobs("image") == []
    assert await cover_row(model_off, fid) is None


async def test_cover_is_bought_reserved_first_settled_after_and_served(env: Env) -> None:
    fid = await env.new_family_world()
    assert await env.drain_images() == 1
    assert len(env.requests) == 1
    assert [(r["state"], r["actual_micro_usd"]) for r in env.reserved_at_call[0]] == [
        ("reserved", None)
    ]
    (spend,) = await env.spend()
    assert spend["state"] == "settled" and spend["actual_micro_usd"] == 33600
    assert spend["reserved_micro_usd"] > 45_000
    cover = (await env.client.get(PATH.format(fid), headers=env.adult)).json()["cover"]
    assert cover["status"] == "ready"
    r = await env.client.get(cover["url"], headers=env.adult)
    assert r.headers["content-type"] == "image/webp"
    img = Image.open(io.BytesIO(r.content))
    assert img.format == "WEBP" and max(img.size) <= 1024
    assert (await env.jobs("image"))[0]["status"] == "done"


async def test_request_prompt_has_no_family_data_and_the_safety_ending(env: Env) -> None:
    await env.new_family_world()
    await env.drain_images()
    prompt = env.requests[0]["messages"][0]["content"]
    for word in ("Anya", "Bobby", "Smith", "dinosaurs", "trains", "6-9"):
        assert word.lower() not in prompt.lower()
    assert not any(ch.isdigit() for ch in prompt)
    assert "no people" in prompt and "no text" in prompt
    assert "Moon Harbor" in prompt
    body = env.requests[0]
    assert body["modalities"] == ["image"] and "temperature" not in body
    assert body["provider"]["zdr"] is True


async def test_stale_world_is_skipped_without_a_call(env: Env) -> None:
    fid = await env.new_family_world()
    r = await env.client.post(PATH.format(fid), headers=env.adult, json={"genre": "space"})
    assert r.status_code == 202  # the world is regenerated: the first cover job is stale
    assert await env.jobs("image")
    n = len(await env.jobs("world"))
    assert n == 2
    # drain only the image job; the pending world is not ready
    assert await env.image.run_once() is True
    assert env.requests == [] and await env.spend() == []
    assert (await env.jobs("image"))[0]["status"] == "done"


async def test_over_cap_defers_the_cover_to_the_next_day_without_spending_an_attempt(
    postgres_url: str, agent, db_fetch
) -> None:
    async for e in build(postgres_url, agent, db_fetch, image_global_daily_cap_usd=0.1):
        await e.db_fetch(  # the day's global image money is mostly spent already
            "INSERT INTO llm_spend (job_id, attempt, reserved_micro_usd, kind)"
            " VALUES (gen_random_uuid(), 1, 100000, 'image') RETURNING id"
        )
        fid = await e.new_family_world()
        assert await e.drain_images() == 1  # claimed once; the deferred job is not due today
        assert e.requests == [] and len(await e.spend()) == 1  # only the seeded row
        assert (await cover_row(e, fid))["status"] == "pending"
        (job,) = await e.jobs("image")
        assert (job["status"], job["attempts"], job["last_error"]) == ("pending", 0, None)
        (ahead,) = await e.db_fetch(
            "SELECT next_run_at > now() AS later, next_run_at - now() <= interval '1 day' AS soon,"
            " to_char(next_run_at AT TIME ZONE 'UTC', 'HH24:MI:SS') = '00:00:00' AS midnight"
            " FROM jobs WHERE kind = 'image'"
        )
        assert ahead["later"] and ahead["soon"] and ahead["midnight"]
        got = (await e.client.get(PATH.format(fid), headers=e.adult)).json()
        assert got["cover"] == {"status": "pending", "url": None, "deferred": True}
        assert await e.image.run_once() is False  # nothing due until the budget resets


async def test_a_cap_below_one_picture_fails_the_cover_for_good(
    postgres_url: str, agent, db_fetch
) -> None:
    async for e in build(postgres_url, agent, db_fetch, image_family_daily_cap_usd=0.01):
        fid = await e.new_family_world()
        await e.drain_images()
        assert e.requests == [] and await e.spend() == []
        assert (await cover_row(e, fid))["status"] == "failed"
        (job,) = await e.jobs("image")
        assert job["status"] == "failed"
        got = (await e.client.get(PATH.format(fid), headers=e.adult)).json()
        assert got["status"] == "ready" and got["cover"]["status"] == "failed"
        assert got["cover"]["deferred"] is False


async def test_deferred_cover_is_drawn_once_the_budget_is_back_and_orders_the_scene(
    postgres_url: str, agent, db_fetch
) -> None:
    async for e in build(postgres_url, agent, db_fetch, image_global_daily_cap_usd=0.1):
        await e.db_fetch(  # the day's global image money is already spent
            "INSERT INTO llm_spend (job_id, attempt, reserved_micro_usd, kind)"
            " VALUES (gen_random_uuid(), 1, 100000, 'image') RETURNING id"
        )
        fid = await e.new_family_world()
        await e.drain_images()
        assert e.requests == []
        await e.db_fetch("DELETE FROM llm_spend")  # the next UTC day starts with a clean sheet
        await e.db_fetch("UPDATE jobs SET next_run_at = now() WHERE kind = 'image' RETURNING id")
        assert await e.drain_images() == 1
        assert len(e.requests) == 1
        assert (await cover_row(e, fid))["status"] == "ready"
        got = (await e.client.get(PATH.format(fid), headers=e.adult)).json()
        assert got["cover"]["status"] == "ready" and got["cover"]["deferred"] is False


async def test_a_retry_wait_is_not_reported_as_deferred(postgres_url: str, agent, db_fetch) -> None:
    async for e in build(postgres_url, agent, db_fetch, world_retry_delay_s=30):
        e.http_status[:] = [500, 200]
        fid = await e.new_family_world()
        await e.image.run_once()  # the first attempt fails; the retry waits 30 s
        (wait,) = await e.db_fetch(
            "SELECT status, next_run_at > now() AS later FROM jobs WHERE kind = 'image'"
        )
        assert (wait["status"], wait["later"]) == ("pending", True)
        got = (await e.client.get(PATH.format(fid), headers=e.adult)).json()
        assert got["cover"]["status"] == "pending" and got["cover"]["deferred"] is False


async def test_second_failure_marks_the_cover_failed_and_the_world_stays_ready(env: Env) -> None:
    env.http_status[:] = [500, 500, 200]
    fid = await env.new_family_world()
    await env.drain_images()
    assert len(env.requests) == 2  # never a third attempt
    rows = await env.spend()
    assert [(r["attempt"], r["state"]) for r in rows] == [(1, "reserved"), (2, "reserved")]
    assert (await cover_row(env, fid))["status"] == "failed"
    got = (await env.client.get(PATH.format(fid), headers=env.adult)).json()
    assert got["status"] == "ready" and got["world"] is not None
    assert (await env.jobs("image"))[0]["status"] == "failed"


async def test_one_failure_then_success_keeps_the_first_reservation(env: Env) -> None:
    env.http_status[:] = [500, 200]
    fid = await env.new_family_world()
    await env.drain_images()
    rows = await env.spend()
    assert [r["state"] for r in rows] == ["reserved", "settled"]
    assert (await cover_row(env, fid))["status"] == "ready"


async def test_actual_above_the_reserve_logs_an_error_and_stops_the_worker(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    env.cost[0] = 0.5
    fid = await env.new_family_world()
    with caplog.at_level(logging.ERROR):
        await env.drain_images()
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert env.image.halted
    (spend,) = await env.spend()
    assert spend["actual_micro_usd"] == 500_000  # the real charge is recorded
    assert (await cover_row(env, fid))["status"] == "ready"


async def test_absurd_cost_halts_without_storing_it(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    env.cost[0] = 1e308
    fid = await env.new_family_world()
    with caplog.at_level(logging.ERROR):
        await env.drain_images()
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert env.image.halted
    (spend,) = await env.spend()
    assert spend["state"] == "settled"
    assert spend["actual_micro_usd"] == 1_000_000  # settled at the global image cap
    assert (await cover_row(env, fid))["status"] == "ready"


@pytest.fixture
async def cap_half(postgres_url: str, agent, db_fetch) -> AsyncIterator[Env]:
    async for e in build(postgres_url, agent, db_fetch, image_global_daily_cap_usd=0.5):
        yield e


@pytest.mark.parametrize(
    ("cost", "implausible"), [(0.5, False), (0.500001, True)], ids=["at-cap", "cap-plus-1"]
)
async def test_cost_boundary_is_the_global_image_cap(
    cap_half: Env, caplog: pytest.LogCaptureFixture, cost: float, implausible: bool
) -> None:
    cap_half.cost[0] = cost
    await cap_half.new_family_world()
    with caplog.at_level(logging.ERROR):
        await cap_half.drain_images()
    (spend,) = await cap_half.spend()
    assert spend["actual_micro_usd"] == 500_000  # as reported at the cap, clamped above it
    errors = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
    assert ("implausible" in errors) is implausible
    assert cap_half.image.halted  # 0.5 USD is above the reserve either way


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(postgres_url)
    yield e
    await e.dispose()


async def test_without_image_model_the_worker_does_not_start(
    postgres_url: str, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The client refuses an empty model too; stub it so only the guard in main is under test.
    monkeypatch.setattr("app.main.OpenRouterImageClient", lambda settings: object())
    off = settings(postgres_url, image_model="", world_worker_enabled=True)
    assert _start_image_worker(engine, off) is None
    monkeypatch.undo()
    no_key = settings(postgres_url, openrouter_api_key=None, world_worker_enabled=True)
    assert _start_image_worker(engine, no_key) is None
    disabled = settings(postgres_url, world_worker_enabled=False)
    assert _start_image_worker(engine, disabled) is None


async def test_with_image_model_and_key_the_worker_starts(
    postgres_url: str, engine: AsyncEngine
) -> None:
    on = settings(postgres_url, world_worker_enabled=True)
    task = _start_image_worker(engine, on)
    assert task is not None
    await _stop_worker(task)


@pytest.fixture
async def cap_tenth(postgres_url: str, agent, db_fetch) -> AsyncIterator[Env]:
    async for e in build(postgres_url, agent, db_fetch, image_family_daily_cap_usd=0.10):
        yield e


async def test_third_picture_of_a_day_is_over_cap_at_a_tenth(cap_tenth: Env) -> None:
    env = cap_tenth
    fid = await env.new_family_world()
    await env.drain_images()
    for _ in range(2):  # regenerations: three worlds a day is the limit
        await env.client.post(PATH.format(fid), headers=env.adult, json={"genre": "space"})
        while await env.world.run_once():
            pass
        await env.drain_images()
    assert len(env.requests) == 2  # 2 x 0.0336 settled; the third reserve no longer fits 0.10
    got = (await env.client.get(PATH.format(fid), headers=env.adult)).json()
    assert got["cover"] == {"status": "pending", "url": None, "deferred": True}
    assert len(await env.spend()) == 2


async def test_run_forever_stops_after_an_overcharge(env: Env) -> None:
    env.cost[0] = 0.5
    await env.new_family_world()
    await env.new_family_world()
    assert len(await env.jobs("image")) == 2
    await asyncio.wait_for(env.image.run_forever(), timeout=10)
    assert len(env.requests) == 1  # the second queued picture is never bought
    assert env.image.halted
