import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

import httpx2
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent.chapter_writer import build_chapter_writer
from app.agent.image_client import OpenRouterImageClient
from app.domain.adventure import growth_cover_milestone, milestone_number
from app.domain.world import World, with_image_prompts
from app.main import create_app
from app.repositories.job_repository import JobRepository
from app.services.cover_prompt import GrowthStory, growth_cover_prompt
from app.workers.chapter_worker import ChapterWorker
from app.workers.image_worker import ImageWorker
from tests.conftest import _client
from tests.test_adventure_api import DONE
from tests.test_chapter_worker import CHAPTER, Env, adventure, finish_quest, make_settings
from tests.test_cover_worker import COST, picture, settings
from tests.test_scene_worker import ON
from tests.test_world import world_args

WORLD_PATH = "/api/v1/families/{}/world"


class Growth(Env):
    db_fetch: Callable[..., Awaitable[list]]
    image: ImageWorker
    prompts: list[str]
    no_milestone: bool
    adult: dict
    fid: str

    async def begin(self) -> None:
        """Chapter 1 stored, the family's world ready."""
        self.adult, self.fid, _ = await finish_quest(self)
        await ready_world(self, self.fid)
        await self.drain()

    async def advance(self, chapters: int = 1) -> None:
        for _ in range(chapters):
            quest = (await adventure(self, self.adult, self.fid))["quest"]
            done = DONE.format(quest["id"])
            await self.client.post(done, headers=self.adult, json={"note": "again"})
            await self.drain()

    async def images(self) -> list:
        return await self.db_fetch(
            "SELECT kind, milestone_no, status, sha256 FROM world_images WHERE family_id = $1"
            " ORDER BY milestone_no",
            UUID(self.fid),
        )

    async def old_cover(self) -> str:
        """A ready first cover, as the world worker and image worker leave it."""
        (job,) = await self.db_fetch(
            "SELECT job_id FROM worlds WHERE family_id = $1", UUID(self.fid)
        )
        await self.db_fetch(
            "INSERT INTO world_images"
            " (family_id, world_job_id, kind, prompt, status, sha256, bytes)"
            " VALUES ($1, $2, 'cover', 'first', 'ready', $3, $4)",
            UUID(self.fid), job["job_id"], OLD_SHA, b"old",
        )  # fmt: skip
        return OLD_SHA

    async def world(self) -> dict:
        return (await self.client.get(WORLD_PATH.format(self.fid), headers=self.adult)).json()

    async def cover_url(self) -> str | None:
        got = await self.client.get(WORLD_PATH.format(self.fid), headers=self.adult)
        return (got.json()["cover"] or {}).get("url")


OLD_SHA = "a" * 64
WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen".split()
)  # scrub drops digits


async def ready_world(env: Growth, fid: str) -> None:
    world = with_image_prompts(World.model_validate(world_args([])), "space", ["Anya", "dinos"])
    await env.db_fetch(
        "UPDATE worlds SET status = 'ready', world = CAST($2 AS jsonb) WHERE family_id = $1",
        UUID(fid),
        world.model_dump_json(),
    )


async def build(
    postgres_url: str, agent, db_fetch, chapter_image_model: str = "vendor/img", **extra: Any
) -> AsyncIterator[Growth]:
    await db_fetch("DELETE FROM jobs")
    await db_fetch("DELETE FROM llm_spend")
    cfg = make_settings(postgres_url, image_model=chapter_image_model).model_copy(
        update={"chapter_timeout_s": 10}  # a loaded machine must not turn a chapter into a retry
    )
    writer = build_chapter_writer(cfg)
    state = Growth.__new__(Growth)
    state.prompts, state.no_milestone = [], False

    async def script(messages, info) -> ModelResponse:
        prompt = json.dumps([str(m) for m in messages])
        found = re.search(r'chapter_number\\+": (\d+)', prompt)
        assert found
        number = int(found[1])
        beat = re.search(r'beat\\+": \\+"(\w+)', prompt)
        answer = {**CHAPTER, "summary": f"Bobby saw 7 trains. Summary {WORDS[number]}"}
        if beat and beat[1] == "milestone" and not state.no_milestone:
            answer["milestone"] = f"Anya found 3 dinosaurs, Milestone line {WORDS[number]}"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    async def handler(request: httpx2.Request) -> httpx2.Response:
        state.prompts.append(json.loads(request.content)["messages"][0]["content"])
        body = {
            "choices": [{"message": {"images": [{"image_url": {"url": picture()}}]}}],
            "usage": {"cost": COST},
        }
        return httpx2.Response(200, json=body)

    app = create_app(cfg, agent=agent)
    with writer.agent.override(model=FunctionModel(script)):
        async for c in _client(app):
            img_cfg = settings(postgres_url, **extra)
            http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
            client_ = OpenRouterImageClient(img_cfg, http_client=http)
            state.__init__(c, ChapterWorker(app.state.engine, writer, cfg), writer)
            state.db_fetch, state.image = db_fetch, ImageWorker(app.state.engine, client_, img_cfg)
            yield state


@pytest.fixture
async def grow(postgres_url: str, agent, db_fetch) -> AsyncIterator[Growth]:
    async for e in build(postgres_url, agent, db_fetch):
        yield e


async def image_jobs(env: Growth) -> list[dict]:
    rows = await env.db_fetch("SELECT payload FROM jobs WHERE kind = 'image' ORDER BY created_at")
    return [json.loads(r["payload"]) for r in rows]


async def drain_images(env: Growth) -> None:
    while await env.image.run_once():
        pass


def test_every_second_milestone_chapter_earns_a_cover() -> None:
    numbers = [milestone_number(n) for n in range(1, 10)]
    assert numbers == [None, None, 1, None, None, 2, None, None, 3]
    assert [n for n in range(1, 13) if growth_cover_milestone(n)] == [6, 12]


async def test_milestone_2_orders_a_cover_1_and_3_do_not(grow: Growth) -> None:
    await grow.begin()
    await grow.advance(2)  # chapter 3: milestone 1
    assert await image_jobs(grow) == []
    await grow.advance(3)  # chapter 6: milestone 2
    (job,) = await image_jobs(grow)
    assert job["milestone_no"] == 2 and set(job) == {"world_job_id", "milestone_no"}
    await grow.advance(3)  # chapter 9: milestone 3
    assert len(await image_jobs(grow)) == 1


async def test_a_chapter_run_twice_orders_the_cover_once(grow: Growth) -> None:
    await grow.begin()
    await grow.advance(5)
    fam = UUID(grow.fid)
    (chapter,) = await grow.db_fetch(
        "SELECT id, job_id FROM chapters WHERE seq = 6 AND family_id = $1", fam
    )
    (old,) = await grow.db_fetch("SELECT payload FROM jobs WHERE id = $1", chapter["job_id"])
    async with grow.worker._engine.begin() as conn:  # a retry: a new job owns the stored chapter
        retry = await JobRepository(conn).enqueue(
            "chapter", UUID(grow.fid), json.loads(old["payload"])
        )
    await grow.db_fetch(
        "UPDATE chapters SET status = 'queued', job_id = $2 WHERE id = $1", chapter["id"], retry
    )
    await grow.drain()
    assert len(await image_jobs(grow)) == 1 and len(await grow.images()) == 1


async def test_no_milestone_line_orders_no_cover(grow: Growth) -> None:
    grow.no_milestone = True
    await grow.begin()
    await grow.advance(5)
    chapters = (await adventure(grow, grow.adult, grow.fid))["chapters"]
    assert chapters[5]["status"] == "ready" and chapters[5]["milestone"] is None
    assert await image_jobs(grow) == [] and await grow.images() == []


async def test_image_model_off_orders_no_cover(postgres_url: str, agent, db_fetch) -> None:
    async for e in build(postgres_url, agent, db_fetch, chapter_image_model=""):
        await e.begin()
        await e.advance(5)
        assert await image_jobs(e) == []


async def test_growth_cover_keeps_the_old_one_in_history_and_becomes_current(grow: Growth) -> None:
    await grow.begin()
    old = await grow.old_cover()
    await grow.advance(5)
    await drain_images(grow)
    rows = await grow.images()
    assert [(r["kind"], r["milestone_no"], r["status"]) for r in rows] == [
        ("cover", 0, "ready"),
        ("cover_growth", 2, "ready"),
    ]
    assert rows[0]["sha256"] == old and rows[1]["sha256"] != old
    assert await grow.cover_url() == f"/api/v1/media/{rows[1]['sha256']}.webp"
    assert (await grow.world())["cover_growing"] is False


async def test_cover_stays_the_old_one_while_the_new_is_pending(grow: Growth) -> None:
    await grow.begin()
    await grow.old_cover()
    await grow.advance(5)
    assert await grow.cover_url() == f"/api/v1/media/{OLD_SHA}.webp"
    assert (await grow.world())["cover_growing"] is True
    await drain_images(grow)
    assert (await grow.world())["cover_growing"] is False


async def test_cover_growing_is_false_before_any_growth_cover(grow: Growth) -> None:
    await grow.begin()
    await grow.old_cover()
    assert (await grow.world())["cover_growing"] is False
    await grow.advance(2)  # chapter 3: milestone 1 orders nothing
    assert (await grow.world())["cover_growing"] is False


async def test_a_pending_growth_cover_of_a_previous_world_is_not_growing(grow: Growth) -> None:
    await grow.begin()
    await grow.old_cover()
    await grow.advance(5)
    assert (await grow.world())["cover_growing"] is True
    await grow.db_fetch(  # the world is regenerated: its job changes, the old row stays pending
        "UPDATE worlds SET job_id = gen_random_uuid() WHERE family_id = $1", UUID(grow.fid)
    )
    assert (await grow.world())["cover_growing"] is False


async def test_a_growth_cover_orders_no_3d_scene(postgres_url: str, agent, db_fetch) -> None:
    async for e in build(postgres_url, agent, db_fetch, chapter_image_model="vendor/img", **ON):
        await e.begin()  # no first cover: only the growth cover is stored for this world
        await e.advance(5)
        await drain_images(e)
        assert [r["status"] for r in await e.images()] == ["ready"]
        scenes = "SELECT count(*) AS n FROM world_scenes WHERE family_id = $1"
        assert (await db_fetch(scenes, UUID(e.fid)))[0]["n"] == 0


async def test_prompt_lists_only_the_milestones_of_the_current_world(grow: Growth) -> None:
    await grow.begin()
    await grow.advance(2)  # chapter 3: milestone "three" belongs to the first world
    await grow.db_fetch(  # the world is regenerated: a new world became ready after it
        "UPDATE worlds SET updated_at = now() - interval '30 minutes' WHERE family_id = $1",
        UUID(grow.fid),
    )
    await grow.db_fetch(
        "UPDATE chapters SET created_at = now() - interval '1 hour' WHERE family_id = $1",
        UUID(grow.fid),
    )
    await grow.advance(3)
    await drain_images(grow)
    (prompt,) = grow.prompts
    assert "Milestone line six" in prompt and "Milestone line three" not in prompt


async def test_prompt_shows_the_newest_milestone_without_family_data(grow: Growth) -> None:
    await grow.begin()
    await grow.advance(5)
    await drain_images(grow)
    (prompt,) = grow.prompts
    assert "Milestone line three" in prompt and "Milestone line six" in prompt
    assert prompt.index("Milestone line three") < prompt.index("Milestone line six")
    assert (
        "The newest change, found, Milestone line six, is the clear focus" in prompt
    )  # the rest of the line is scrubbed
    assert "Do not repaint the earlier scene" in prompt and "Summary six" in prompt
    assert "Moon Harbor" in prompt and "no people" in prompt and "no text" in prompt
    assert not any(ch.isdigit() for ch in prompt)
    for private in ("anya", "bobby", "smith", "dinosaurs", "trains"):
        assert private not in prompt.lower()


async def test_at_the_image_cap_the_chapter_is_stored_and_no_paid_call_runs(
    postgres_url: str, agent, db_fetch
) -> None:
    async for e in build(postgres_url, agent, db_fetch, image_family_daily_cap_usd=0.01):
        await e.begin()
        await e.old_cover()
        await e.advance(5)
        await drain_images(e)
        got = await adventure(e, e.adult, e.fid)
        assert got["chapters"][5]["status"] == "ready" and got["chapters"][5]["milestone"]
        assert e.prompts == []
        spend = await db_fetch("SELECT kind FROM llm_spend")
        assert {r["kind"] for r in spend} == {"text"}
        assert [r["status"] for r in await e.images()] == ["ready", "failed"]
        assert await e.cover_url() == f"/api/v1/media/{OLD_SHA}.webp"
        assert (await e.world())["cover_growing"] is False  # a refused cover is not growing


def test_growth_prompt_scrubs_declined_cyrillic_names_interests_and_digits() -> None:
    story = GrowthStory(
        "тёплый",
        "У Ани есть 5 динозавров и маяк",
        ["Аня нашла 3 динозавра", "Аню позвали к новому маяку"],
    )
    prompt = growth_cover_prompt(
        "space, Moon Harbor", story, banned=["Аня", "динозавр"], young_child=False
    )
    for private in ("Аня", "Ани", "Аню", "динозавр"):
        assert private not in prompt
    assert not any(ch.isdigit() for ch in prompt)
    assert "новому маяку" in prompt and "Moon Harbor" in prompt


def test_growth_prompt_scrubs_a_cjk_name_inside_a_sentence() -> None:
    story = GrowthStory("warm", "小明在山上", ["小明找到了新灯塔"])
    prompt = growth_cover_prompt("space", story, banned=["小明"], young_child=True)
    assert "小明" not in prompt and "新灯塔" in prompt
