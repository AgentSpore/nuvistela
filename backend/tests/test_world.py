import json
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.world_generator import build_world_generator
from app.core.config import Settings
from app.main import create_app
from app.repositories.job_repository import JobRepository
from app.workers.world_worker import WorldWorker
from tests.conftest import _client
from tests.test_world_api import PATH, adult_with_child


def world_args(member_ids: list[str], echo: str = "") -> dict:
    return {
        "title": "Moon Harbor",
        "setting": "A harbor above the clouds",
        "tone": "warm",
        "locations": [
            {"name": f"Place {i}", "description": f"A bright place {i} {echo}"} for i in range(4)
        ],
        "heroes": [
            {"member_id": m, "hero_class": "Scout", "trait": "brave", "skill": "tidying"}
            for m in member_ids
        ],
        "prologue": "The harbor wakes up.",
    }


@dataclass
class Env:
    app: FastAPI
    client: AsyncClient
    worker: WorldWorker
    prompts: list[str]
    fail: list[bool | Exception]  # truthy = next generator call fails
    echo: list[str]  # text the "model" echoes into location descriptions

    async def drain(self) -> int:
        n = 0
        while await self.worker.run_once():
            n += 1
        return n


@pytest.fixture
async def env(postgres_url: str, agent, db_fetch):
    await db_fetch("DELETE FROM jobs")  # leftovers of other tests would eat scripted failures
    settings = Settings(
        database_url=postgres_url,
        cookie_secure=False,
        world_worker_enabled=False,
        world_retry_delay_s=0,
        world_model="vendor/world-x",
        openrouter_api_key=SecretStr("k"),
    )
    gen = build_world_generator(settings)
    prompts: list[str] = []
    fail: list[bool | Exception] = []
    echo: list[str] = [""]

    def script(messages, info) -> ModelResponse:
        prompts.append(json.dumps([str(m) for m in messages]))
        if fail and (failure := fail.pop(0)):
            raise failure if isinstance(failure, Exception) else ModelAPIError("m", "boom")
        ids = [
            line.split("member_id=")[1].split()[0]
            for line in prompts[-1].replace("\\n", "\n").splitlines()
            if "member_id=" in line
        ]
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, world_args(ids, echo[0]))]
        )

    app = create_app(settings, agent=agent, world_generator=gen)
    with gen.agent.override(model=FunctionModel(script)):
        async for c in _client(app):
            worker = WorldWorker(app.state.engine, gen, settings)
            yield Env(app, c, worker, prompts, fail, echo)


async def test_world_is_generated_without_names_or_ages_in_prompts(env: Env) -> None:
    adult, child, fid, adult_id, child_id = await adult_with_child(env.client)
    env.echo[0] = "with Bobby and Anya aged 6-9 who love trains and dinosaurs"
    r = await env.client.post(PATH.format(fid), headers=adult, json={"genre": "pirates"})
    assert r.json()["status"] == "pending"
    got = (await env.client.get(PATH.format(fid), headers=child)).json()
    assert got["status"] == "pending" and got["world"] is None
    assert await env.drain() == 1
    got = (await env.client.get(PATH.format(fid), headers=child)).json()
    assert got["status"] == "ready"
    assert {h["member_id"] for h in got["world"]["heroes"]} == {adult_id, child_id}
    sent = " ".join(env.prompts)
    assert "Bobby" not in sent and "Anya" not in sent and "Smith" not in sent
    assert "trains" in sent  # interests do reach the text model
    images = [x["image_prompt"] for x in got["world"]["locations"] + got["world"]["heroes"]]
    images.append(got["world"]["cover_image_prompt"])
    assert all(images)
    blob = " ".join(images).lower()
    for banned in ("bobby", "anya", "6-9", "trains", "dinosaurs", "smith"):
        assert banned not in blob


async def test_three_failures_give_genre_fallback(env: Env) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.fail[:] = [True, True, True]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    assert await env.drain() == 3
    got = (await env.client.get(PATH.format(fid), headers=adult)).json()
    assert got["status"] == "fallback"
    assert len(got["world"]["heroes"]) == 2
    assert 4 <= len(got["world"]["locations"]) <= 6


async def test_chat_context_carries_world_summary(env: Env) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    seen: list[str | None] = []

    def reply(messages, info) -> ModelResponse:
        seen.append(messages[-1].instructions)
        return ModelResponse(parts=[TextPart("ok")])

    state = env.app.state
    with state.agent.override(model=FunctionModel(reply)):

        async def post():
            return await env.client.post(
                "/api/v1/agent/messages", headers=adult, json={"text": "hi"}
            )

        await post()
        assert "Moon Harbor" not in str(seen[-1])
        await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
        await env.drain()
        await post()
    assert "Moon Harbor" in str(seen[-1]) and "Scout" in str(seen[-1])


async def test_custom_genre_text_stays_out_of_image_prompts(env: Env) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.echo[0] = "a Dragon Bakery town"
    body = {"genre": "custom", "custom_genre": "Dragon Bakery"}
    await env.client.post(PATH.format(fid), headers=adult, json=body)
    await env.drain()
    world = (await env.client.get(PATH.format(fid), headers=adult)).json()["world"]
    blob = " ".join(x["image_prompt"] for x in world["locations"] + world["heroes"]).lower()
    assert blob and "dragon" not in blob and "bakery" not in blob


async def test_job_payload_holds_no_names_or_interests(env: Env, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    (row,) = await db_fetch("SELECT payload::text AS p FROM jobs WHERE family_id = $1", UUID(fid))
    for private in ("Bobby", "Anya", "trains", "dinosaurs"):
        assert private not in row["p"]
    await env.drain()
    assert "trains" in " ".join(env.prompts)  # the worker still reads interests from members


async def test_superseded_job_cannot_overwrite_newer_world(env: Env) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.fail[:] = [True, True, True]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    await env.worker.run_once()
    await env.worker.run_once()  # job A is on its last attempt
    await env.client.post(PATH.format(fid) + "/regenerate", headers=adult)
    await env.worker.run_once()  # A exhausts: its fallback must not replace B
    got = (await env.client.get(PATH.format(fid), headers=adult)).json()
    assert got["status"] == "pending"
    await env.drain()
    assert (await env.client.get(PATH.format(fid), headers=adult)).json()["status"] == "ready"


async def test_unexpected_error_counts_as_an_attempt(env: Env, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.fail[:] = [RuntimeError("boom")]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    await env.worker.run_once()
    (row,) = await db_fetch(
        "SELECT status, attempts, last_error FROM jobs WHERE family_id = $1", UUID(fid)
    )
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "RuntimeError")
    await env.drain()


async def test_crash_looping_job_ends_in_fallback_without_model_call(env: Env, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    for _ in range(3):  # a worker that dies after claiming, three times
        async with env.app.state.engine.begin() as conn:
            assert await JobRepository(conn).claim(["world"]) is not None
        await db_fetch("UPDATE jobs SET locked_at = now() - interval '1 hour'")
    assert await env.worker.run_once()
    assert (await env.client.get(PATH.format(fid), headers=adult)).json()["status"] == "fallback"
    assert env.prompts == []


async def test_lifespan_waits_for_worker_before_disposing_engine(
    postgres_url: str, agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=postgres_url,
        world_model="vendor/world-x",
        openrouter_api_key=SecretStr("k"),
    )
    app = create_app(settings, agent=agent, world_generator=build_world_generator(settings))
    done_at_dispose: list[bool] = []
    real_dispose = AsyncEngine.dispose

    async def dispose(self: AsyncEngine, close: bool = True) -> None:
        done_at_dispose.append(app.state.world_worker.done())
        await real_dispose(self, close)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    async with app.router.lifespan_context(app):
        assert not app.state.world_worker.done()
    assert done_at_dispose and all(done_at_dispose)


async def test_superseded_job_is_completed_without_calling_the_model(env: Env, db_fetch) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.fail[:] = [True]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    await env.worker.run_once()  # job A fails once and waits for a retry
    await env.client.post(PATH.format(fid) + "/regenerate", headers=adult)
    await env.drain()
    assert len(env.prompts) == 2  # A's failed call and B's call; A's retry is skipped
    rows = await db_fetch("SELECT status FROM jobs WHERE family_id = $1", UUID(fid))
    assert [r["status"] for r in rows] == ["done", "done"]
    assert (await env.client.get(PATH.format(fid), headers=adult)).json()["status"] == "ready"
