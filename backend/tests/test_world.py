import asyncio
import json
import re
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.address_rules import ADDRESS_RULES
from app.agent.reaction_rules import REACTION_RULES
from app.agent.world_generator import INSTRUCTIONS, build_world_generator
from app.core.config import Settings
from app.domain.adventure import REACTION_MAX
from app.domain.world import LONG_MAX, GeneratedWorld, World
from app.main import create_app
from app.repositories.job_repository import JobRepository
from app.workers.world_worker import WorldWorker
from tests.conftest import _client
from tests.test_adventure_api import START
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
        "first_quest": {
            "title": "Light the harbor lamp",
            "description": "Draw a lamp on paper and set it in the window.",
            "skill": "care",
            "reaction": "The harbor lamp wakes and the old keeper nods from the pier.",
            "kind": "make",
        },
    }


@dataclass
class Env:
    app: FastAPI
    client: AsyncClient
    worker: WorldWorker
    prompts: list[str]
    fail: list[bool | str | Exception]  # truthy = next generator call fails
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
        world_timeout_s=0.5,
        openrouter_api_key=SecretStr("k"),
    )
    gen = build_world_generator(settings)
    prompts: list[str] = []
    fail: list[bool | str | Exception] = []
    echo: list[str] = [""]

    async def script(messages, info) -> ModelResponse:
        prompts.append(json.dumps([str(m) for m in messages]))
        if fail and (failure := fail.pop(0)):
            if failure == "hang":
                await asyncio.Event().wait()
            raise failure if isinstance(failure, Exception) else ModelAPIError("m", "boom")
        ids = re.findall(r'member_id\\+": \\+"([0-9a-f-]{36})', prompts[-1])
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, world_args(ids, echo[0]))]
        )

    app = create_app(settings, agent=agent, world_generator=gen)
    with gen.agent.override(model=FunctionModel(script)):
        async for c in _client(app):
            app.state.world_worker = True  # the test drives the worker by hand: jobs are processed
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
    body = {"genre": "custom", "custom_genre": "A town of Dragon Bakery"}
    await env.client.post(PATH.format(fid), headers=adult, json=body)
    await env.drain()
    world = (await env.client.get(PATH.format(fid), headers=adult)).json()["world"]
    blob = " ".join(x["image_prompt"] for x in world["locations"] + world["heroes"]).lower()
    assert blob and "dragon" not in blob and "bakery" not in blob


async def test_own_description_keeps_its_plain_words_in_image_prompts(env: Env) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.echo[0] = "город улиток у Барсика в Комарово"
    body = {"genre": "custom", "custom_genre": "город улиток, кот Барсик, дача в Комарово"}
    await env.client.post(PATH.format(fid), headers=adult, json=body)
    await env.drain()
    world = (await env.client.get(PATH.format(fid), headers=adult)).json()["world"]
    blob = " ".join(x["image_prompt"] for x in world["locations"] + world["heroes"]).lower()
    assert "улиток" in blob and "барсик" not in blob and "комарово" not in blob


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


async def test_timed_out_world_call_keeps_its_reserve_unsettled_and_the_retry_succeeds(
    env: Env, db_fetch
) -> None:
    await db_fetch("DELETE FROM llm_spend")
    adult, _, fid, *_ = await adult_with_child(env.client)
    env.fail[:] = ["hang"]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "pirates"})
    await asyncio.wait_for(env.drain(), 10)  # the run deadline must end the stuck call
    assert (await env.client.get(PATH.format(fid), headers=adult)).json()["status"] == "ready"
    rows = await db_fetch("SELECT attempt, state, actual_micro_usd FROM llm_spend ORDER BY attempt")
    assert [(r["attempt"], r["state"]) for r in rows] == [(1, "reserved"), (2, "settled")]
    assert rows[0]["actual_micro_usd"] is None


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


async def test_world_job_reserves_and_settles_money_in_the_shared_ledger(
    env: Env, db_fetch
) -> None:
    await db_fetch("DELETE FROM llm_spend")
    adult, _, fid, *_ = await adult_with_child(env.client)
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "pirates"})
    await env.drain()
    (row,) = await db_fetch("SELECT state, reserved_micro_usd, actual_micro_usd FROM llm_spend")
    assert row["state"] == "settled" and 0 < row["actual_micro_usd"] < row["reserved_micro_usd"]


async def test_world_worker_makes_no_call_when_the_money_cap_is_reached(env: Env, db_fetch) -> None:
    await db_fetch("DELETE FROM llm_spend")
    capped = env.app.state.settings.model_copy(update={"llm_family_daily_cap_usd": 0})
    env.worker = WorldWorker(env.app.state.engine, env.worker._generator, capped)
    adult, child, fid, *_ = await adult_with_child(env.client)
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "pirates"})
    await env.drain()
    assert env.prompts == [] and await db_fetch("SELECT 1 FROM llm_spend") == []
    got = (await env.client.get(PATH.format(fid), headers=child)).json()
    assert got["status"] == "fallback"


async def test_provider_refusal_warns_the_operator_once(env: Env, caplog) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    refusal = ModelHTTPError(402, "m", {"error": {"message": "secret-detail"}})
    env.fail[:] = [refusal, refusal, refusal]
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    await env.drain()
    warned = [r.getMessage() for r in caplog.records if "refused the world model" in r.getMessage()]
    assert len(warned) == 1 and "ModelHTTPError status=402" in warned[0]
    assert "secret-detail" not in caplog.text


async def quests(db_fetch, fid: str) -> list:
    return await db_fetch(
        "SELECT seq, source, title, status FROM quests WHERE family_id = $1", UUID(fid)
    )


async def begin(env: Env) -> tuple[dict, dict, str]:
    adult, child, fid, *_ = await adult_with_child(env.client)
    r = await env.client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert r.json() == {"world_status": "pending", "quest": None}
    return adult, child, fid


async def test_success_opens_exactly_one_world_quest_with_the_worlds_text(
    env: Env, db_fetch
) -> None:
    adult, _, fid = await begin(env)
    again = await env.client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert again.json()["quest"] is None  # still no quest while the world is written
    await env.drain()
    got = (await env.client.get(START.format(fid), headers=adult)).json()
    assert got["world"] == {"status": "ready"}
    assert got["quest"]["source"] == "world" and got["quest"]["title"] == "Light the harbor lamp"
    assert got["quest"]["description"] == "Draw a lamp on paper and set it in the window."
    assert got["quest"]["reaction"] == world_args([])["first_quest"]["reaction"]
    assert [(q["seq"], q["source"]) for q in await quests(db_fetch, fid)] == [(1, "world")]


async def test_fallback_world_opens_exactly_one_template_quest(env: Env, db_fetch) -> None:
    adult, _, fid = await begin(env)
    env.fail[:] = [True, True, True]
    await env.drain()
    got = (await env.client.get(START.format(fid), headers=adult)).json()
    assert got["world"] == {"status": "fallback"} and got["quest"]["source"] == "template"
    assert [(q["seq"], q["source"]) for q in await quests(db_fetch, fid)] == [(1, "template")]


async def test_budget_cap_opens_exactly_one_template_quest(env: Env, db_fetch) -> None:
    await db_fetch("DELETE FROM llm_spend")
    capped = env.app.state.settings.model_copy(update={"llm_family_daily_cap_usd": 0})
    env.worker = WorldWorker(env.app.state.engine, env.worker._generator, capped)
    adult, _, fid = await begin(env)
    await env.drain()
    assert env.prompts == []
    assert [(q["seq"], q["source"]) for q in await quests(db_fetch, fid)] == [(1, "template")]


async def test_retries_regeneration_and_concurrent_starts_keep_one_quest(
    env: Env, db_fetch
) -> None:
    adult, _, fid, *_ = await adult_with_child(env.client)
    starts = [
        env.client.post(START.format(fid), headers=adult, json={"genre": "space"}) for _ in range(2)
    ]
    assert [r.status_code for r in await asyncio.gather(*starts)] == [200, 200]
    assert len(await db_fetch("SELECT 1 FROM jobs WHERE family_id = $1", UUID(fid))) == 1
    env.fail[:] = [True]  # one failed attempt, then the retry succeeds
    await env.drain()
    await env.client.post(PATH.format(fid), headers=adult, json={"genre": "pirates"})
    await env.drain()  # a regenerated world must not open a second quest
    assert [(q["seq"], q["source"]) for q in await quests(db_fetch, fid)] == [(1, "world")]


async def test_a_started_family_with_a_finished_world_and_no_quest_gets_the_template(
    env: Env, db_fetch
) -> None:
    adult, _, fid = await begin(env)
    await db_fetch("UPDATE worlds SET status = 'fallback' WHERE family_id = $1", UUID(fid))
    r = await env.client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert r.json()["quest"]["source"] == "template"
    await env.client.post(START.format(fid), headers=adult, json={"genre": "space"})
    assert len(await quests(db_fetch, fid)) == 1


def missing_phrases(text: str, required: list[str]) -> list[str]:
    return [p for p in required if p not in text]


def test_world_prompt_states_the_first_quest_bounds_and_audience_rules() -> None:
    required = [
        "first_quest is required and never omitted",
        "first_quest.title, at most 80 characters; first_quest.description, a clear task, "
        "at most 400 characters; first_quest.skill, the everyday skill it practises as a short "
        "phrase of one to three words, at most 40 characters, not a sentence",
        "It grows out of the prologue, is small and doable at home today by one person or "
        "several, needs no purchase, no going outside and no kitchen tools",
        "is safe for a child of 3-5 without supervision whenever such a member is listed: nothing "
        "tied around the neck or body, no cords, strings, ropes or scarves, no fire, candles or "
        "matches, no small objects that fit in a mouth, no climbing, no water, no sharp tools",
        "an adult playing alone, or adults only, are addressed as adults",
        'with no diminutives and nothing childish such as "little"',
        'in languages with a polite plural "you" use it for adults',
        "so that no gender is assumed",
        "Never use the word family, in any language, for a single player",
        "word it as an invitation, not an order",
        f"first_quest.reaction, one or two sentences, at most {REACTION_MAX} characters",
        REACTION_RULES,
    ]
    assert missing_phrases(INSTRUCTIONS, required) == []
    for phrase in required:  # mutation: the real check reports a phrase removed from the prompt
        assert missing_phrases(INSTRUCTIONS.replace(phrase, ""), required) == [phrase]


def test_world_prompt_separates_setting_from_prologue_and_avoids_gendered_nouns() -> None:
    required = [
        f"setting, two short sentences describing the place in general, at most {LONG_MAX}",
        "the players' arrival (one player or the group, as the field players says) in the "
        "place, never restating the setting, at most",
        "word hero_class, trait and skill there as a phrase that fits any gender (for example "
        "a verb phrase), never a masculine or feminine agent noun",
    ]
    assert missing_phrases(INSTRUCTIONS, required) == []
    for phrase in required:
        assert missing_phrases(INSTRUCTIONS.replace(phrase, ""), required) == [phrase]


def test_world_prompt_carries_the_address_rules_and_defers_the_polite_clause() -> None:
    assert ADDRESS_RULES in INSTRUCTIONS
    assert (
        'in languages with a polite plural "you" use it for adults, except Spanish, '
        "Chinese and Russian, which follow the address rule"
    ) in INSTRUCTIONS


def test_a_world_stored_before_reactions_still_loads_without_one() -> None:
    stored = world_args([])
    del stored["first_quest"]["reaction"]
    assert World.model_validate(stored).first_quest is not None
    with pytest.raises(ValidationError):
        GeneratedWorld.model_validate(stored)
