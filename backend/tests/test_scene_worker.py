import hashlib
import io
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.agent import world3d_client
from app.agent.errors import AgentConfigError
from app.agent.world3d_client import SceneAssets, SceneError, WorldLabsClient
from app.main import _start_scene_worker, _stop_worker
from app.services.cover_prompt import SAFETY_ENDING, YOUNG_CHILD_ENDING
from app.workers.scene_worker import SCENE_ENDING, SceneWorker, scene_prompt
from tests.test_cover_worker import Env, build, settings
from tests.test_world_api import PATH, adult_with_child

SPZ = b"\x1f\x8b\x08fake-splat-bytes"
PANO = b"RIFF\x24\x00\x00\x00WEBPVP8 fake-panorama"
SHA = hashlib.sha256(SPZ).hexdigest()
ON = {"world3d_model": "marble-1.0-draft", "worldlabs_api_key": SecretStr("wl-key")}
PRICE = 230 * 800  # 230 credits at 1250 credits per USD


@dataclass
class FakeScenes:
    db_fetch: Any
    prompts: list[str] = field(default_factory=list)
    spend_at_call: list[list] = field(default_factory=list)
    failures: list[bool] = field(default_factory=list)  # next calls; empty = success
    error: Exception = field(default_factory=lambda: SceneError("FAILED"))  # what a failure raises

    @property
    def price_micro(self) -> int:
        return PRICE

    async def generate(self, prompt: str) -> SceneAssets:
        self.prompts.append(prompt)
        self.spend_at_call.append(
            await self.db_fetch(
                "SELECT state, actual_micro_usd FROM llm_spend WHERE kind = 'world3d'"
            )
        )
        if self.failures and self.failures.pop(0):
            raise self.error
        return SceneAssets(SPZ, PANO)


@dataclass
class Scene:
    env: Env
    fake: FakeScenes
    worker: SceneWorker

    async def drain(self) -> int:
        n = 0
        while await self.worker.run_once():
            n += 1
        return n

    async def ready_cover(self) -> str:
        fid = await self.env.new_family_world()
        await self.env.drain_images()
        return fid

    async def rows(self, table: str, where: str = "true") -> list:
        return await self.env.db_fetch(f"SELECT * FROM {table} WHERE {where}")  # noqa: S608 (test-only; table and where are literals in this file, no user input)


async def make(postgres_url: str, agent, db_fetch, **extra: Any) -> AsyncIterator[Scene]:
    await db_fetch("DELETE FROM world_scenes")
    async for env in build(postgres_url, agent, db_fetch, **{**ON, **extra}):
        fake = FakeScenes(db_fetch)
        cfg = settings(postgres_url, **{**ON, **extra})
        yield Scene(env, fake, SceneWorker(env.app.state.engine, fake, cfg))


@pytest.fixture
async def scene(postgres_url: str, agent, db_fetch) -> AsyncIterator[Scene]:
    async for s in make(postgres_url, agent, db_fetch):
        yield s


@pytest.fixture
async def scene_off(postgres_url: str, agent, db_fetch) -> AsyncIterator[Scene]:
    async for s in make(postgres_url, agent, db_fetch, world3d_model=""):
        yield s


@pytest.fixture
async def scene_tight(postgres_url: str, agent, db_fetch) -> AsyncIterator[Scene]:
    async for s in make(postgres_url, agent, db_fetch, world3d_global_daily_cap_usd=0.20):
        yield s


@pytest.fixture
async def scene_wide(postgres_url: str, agent, db_fetch) -> AsyncIterator[Scene]:
    async for s in make(postgres_url, agent, db_fetch, world3d_family_daily_cap_usd=1.0):
        yield s


async def test_ready_cover_orders_one_scene(scene: Scene) -> None:
    fid = await scene.ready_cover()
    jobs = await scene.env.jobs("scene")
    assert len(jobs) == 1 and json.loads(jobs[0]["payload"]).keys() == {"world_job_id"}
    (row,) = await scene.rows("world_scenes")
    assert row["status"] == "pending" and str(row["family_id"]) == fid
    assert scene.fake.prompts == []  # ordering buys nothing


async def test_no_model_orders_nothing(scene_off: Scene) -> None:
    await scene_off.ready_cover()
    assert await scene_off.env.jobs("scene") == []
    assert await scene_off.rows("world_scenes") == []


async def test_fallback_world_orders_nothing(scene: Scene) -> None:
    scene.env.world_fails[:] = [True, True, True]
    fid = await scene.env.new_family_world()
    await scene.env.drain_images()
    status = (await scene.env.client.get(PATH.format(fid), headers=scene.env.adult)).json()
    assert status["status"] == "fallback" and status["scene"] is None
    assert await scene.env.jobs("scene") == []
    assert await scene.rows("world_scenes") == []


async def test_reserved_before_the_call_settled_at_the_table_price_and_served(
    scene: Scene,
) -> None:
    fid = await scene.ready_cover()
    assert await scene.drain() == 1
    assert [(r["state"], r["actual_micro_usd"]) for r in scene.fake.spend_at_call[0]] == [
        ("reserved", None)
    ]
    (spend,) = await scene.rows("llm_spend", "kind = 'world3d'")
    assert spend["state"] == "settled" and spend["actual_micro_usd"] == PRICE
    world = (await scene.env.client.get(PATH.format(fid), headers=scene.env.adult)).json()
    assert world["scene"] == {
        "status": "ready",
        "url": f"/api/v1/media/{SHA}.spz",
        "panorama_url": f"/api/v1/media/pano/{SHA}.webp",
    }
    r = await scene.env.client.get(world["scene"]["url"], headers=scene.env.adult)
    assert r.content == SPZ
    pano = await scene.env.client.get(world["scene"]["panorama_url"], headers=scene.env.adult)
    assert pano.content == PANO and pano.headers["content-type"] == "image/webp"
    assert (await scene.env.jobs("scene"))[0]["status"] == "done"


async def test_url_is_null_until_ready(scene: Scene) -> None:
    fid = await scene.ready_cover()
    body = (await scene.env.client.get(PATH.format(fid), headers=scene.env.adult)).json()
    assert body["scene"] == {"status": "pending", "url": None, "panorama_url": None}


async def test_panorama_is_private_to_its_family(scene: Scene) -> None:
    await scene.ready_cover()
    await scene.drain()
    url = f"/api/v1/media/pano/{SHA}.webp"
    other, *_ = await adult_with_child(scene.env.client)
    anonymous = await scene.env.client.get(url)
    stranger = await scene.env.client.get(url, headers=other)
    assert (anonymous.status_code, stranger.status_code) == (404, 404)
    assert stranger.json() == anonymous.json() == {"detail": "not found"}


async def test_prompt_has_no_family_data_and_the_scene_ending(scene: Scene) -> None:
    await scene.ready_cover()
    await scene.drain()
    prompt = scene.fake.prompts[0]
    for word in ("Anya", "Bobby", "Smith", "dinosaurs", "trains", "6-9"):
        assert word.lower() not in prompt.lower()
    assert not any(ch.isdigit() for ch in prompt)
    assert prompt.endswith(SCENE_ENDING) and "Moon Harbor" in prompt
    assert prompt.count(SAFETY_ENDING) == 1


def test_young_child_ending_does_not_reach_the_provider() -> None:
    for ending in (SAFETY_ENDING, YOUNG_CHILD_ENDING):
        prompt = scene_prompt(f"A harbor, soft light. {ending}")
        assert prompt == f"A harbor, soft light. {SCENE_ENDING}"


@pytest.mark.parametrize("ending", [SAFETY_ENDING, YOUNG_CHILD_ENDING])
def test_scene_prompt_bans_lettering_once_and_stays_bright(ending: str) -> None:
    prompt = scene_prompt(f"A harbor, soft light. {ending}")
    assert prompt.count("no letters, no words, no labels, no captions, no signs") == 1
    assert prompt.count("no logos, no watermarks") == 1
    assert prompt.endswith("A bright daytime scene, nothing frightening.")


async def test_over_cap_makes_no_call_and_waits_for_the_next_day(
    scene_tight: Scene, caplog: pytest.LogCaptureFixture
) -> None:
    fid = await scene_tight.ready_cover()
    await scene_tight.env.db_fetch(  # the day's global money is mostly spent already
        "INSERT INTO llm_spend (job_id, attempt, reserved_micro_usd, kind)"
        " VALUES (gen_random_uuid(), 1, 100000, 'world3d') RETURNING id"
    )
    caplog.set_level("INFO")
    assert await scene_tight.drain() == 1  # one claim; the deferred job is not due again today
    assert scene_tight.fake.prompts == []
    (row,) = await scene_tight.rows("world_scenes")
    assert row["status"] == "pending"
    (job,) = await scene_tight.env.jobs("scene")
    assert (job["status"], job["attempts"]) == ("pending", 0)  # a no-call costs no attempt
    (ahead,) = await scene_tight.env.db_fetch(
        "SELECT next_run_at > now() AS later,"
        " next_run_at - now() <= interval '1 day' AS within_a_day,"
        " to_char(next_run_at AT TIME ZONE 'UTC', 'HH24:MI:SS') = '00:00:00' AS at_midnight"
        " FROM jobs WHERE kind = 'scene'"
    )
    assert ahead["later"] and ahead["within_a_day"] and ahead["at_midnight"]
    assert any(str(job["id"]) in m and fid in m for m in caplog.messages)
    body = await scene_tight.env.client.get(PATH.format(fid), headers=scene_tight.env.adult)
    assert body.json()["scene"]["status"] == "pending"


async def test_failure_keeps_a_scene_error_message_but_only_the_class_of_anything_else(
    scene: Scene, caplog: pytest.LogCaptureFixture
) -> None:
    await scene.ready_cover()
    scene.fake.failures[:] = [True]
    scene.fake.error = SceneError("HTTP 404")
    with caplog.at_level("WARNING", logger="app.workers.scene_worker"):
        await scene.drain()
    (job,) = await scene.env.jobs("scene")
    assert job["last_error"] == "SceneError: HTTP 404"
    assert "SceneError: HTTP 404 attempt=1" in caplog.text

    await scene.env.db_fetch("UPDATE jobs SET next_run_at = now() WHERE kind = 'scene'")
    await scene.env.db_fetch("DELETE FROM llm_spend")
    scene.fake.failures[:] = [True]
    scene.fake.error = RuntimeError("provider said: secret request detail")
    caplog.clear()
    with caplog.at_level("WARNING", logger="app.workers.scene_worker"):
        await scene.drain()
    (job,) = await scene.env.jobs("scene")
    assert job["last_error"] == "RuntimeError"
    assert "secret" not in caplog.text


async def test_one_failure_then_success_retries_once(scene_wide: Scene) -> None:
    await scene_wide.ready_cover()
    scene_wide.fake.failures[:] = [True]
    await scene_wide.drain()
    assert len(scene_wide.fake.prompts) == 2
    (row,) = await scene_wide.rows("world_scenes")
    assert row["status"] == "ready"
    spends = await scene_wide.rows("llm_spend", "kind = 'world3d' ORDER BY created_at")
    assert [s["state"] for s in spends] == ["reserved", "settled"]  # a failed try keeps its reserve


async def test_two_failures_fail_the_scene_and_a_third_call_never_happens(
    scene_wide: Scene,
) -> None:
    await scene_wide.ready_cover()
    scene_wide.fake.failures[:] = [True, True, True]
    await scene_wide.drain()
    assert len(scene_wide.fake.prompts) == 2  # first try and the one retry, never a third
    (row,) = await scene_wide.rows("world_scenes")
    assert row["status"] == "failed"


async def test_default_cap_allows_one_draft_a_day_so_the_retry_waits(scene: Scene) -> None:
    await scene.ready_cover()
    scene.fake.failures[:] = [True]
    await scene.drain()
    assert len(scene.fake.prompts) == 1
    (row,) = await scene.rows("world_scenes")
    assert row["status"] == "pending"
    (job,) = await scene.env.jobs("scene")
    assert (job["status"], job["attempts"]) == ("pending", 1)  # only the paid call was counted


async def test_third_claim_is_refused_without_a_call(scene: Scene) -> None:
    await scene.ready_cover()
    await scene.env.db_fetch("UPDATE jobs SET attempts = 2 WHERE kind = 'scene'")
    await scene.drain()
    assert scene.fake.prompts == []
    (row,) = await scene.rows("world_scenes")
    assert row["status"] == "failed"


async def test_stale_scene_is_skipped_without_a_call(scene: Scene) -> None:
    await scene.ready_cover()
    await scene.env.db_fetch("UPDATE worlds SET job_id = gen_random_uuid()")
    await scene.drain()
    assert scene.fake.prompts == []
    assert (await scene.env.jobs("scene"))[0]["status"] == "done"


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(postgres_url)
    yield e
    await e.dispose()


async def test_worker_starts_only_with_model_and_key(
    postgres_url: str, engine: AsyncEngine
) -> None:
    for extra in (
        {"world3d_model": ""},
        {"worldlabs_api_key": None},
        {"world_worker_enabled": False},
    ):
        cfg = settings(postgres_url, **{"world_worker_enabled": True, **ON, **extra})
        assert _start_scene_worker(engine, cfg) is None
    task = _start_scene_worker(engine, settings(postgres_url, world_worker_enabled=True, **ON))
    assert task is not None
    await _stop_worker(task)
    unpriced = settings(postgres_url, world_worker_enabled=True, **{**ON, "world3d_model": "x"})
    assert _start_scene_worker(engine, unpriced) is None


# --- World Labs client over a mock transport ---------------------------------------------------

OP = "op-1"
WID = "world-1"


class ChunkedBody(httpx2.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@dataclass
class Api:
    requests: list[httpx2.Request] = field(default_factory=list)
    polls: list[dict | int] = field(default_factory=list)  # answers; int = bare status
    worlds: list[dict] = field(default_factory=lambda: [WORLD])  # world answers, last repeats
    pano: bytes = field(default_factory=lambda: png((64, 32)))
    stream_spz: bool = False  # body without Content-Length, as a chunked response

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.endswith("worlds:generate"):
            return httpx2.Response(200, json={"operation_id": OP, "done": False})
        if url.endswith(f"operations/{OP}"):
            answer = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
            if isinstance(answer, int):
                return httpx2.Response(answer, json={"detail": "Operation not found"})
            return httpx2.Response(200, json=answer)
        if url.endswith(f"worlds/{WID}"):
            return httpx2.Response(
                200, json=self.worlds.pop(0) if len(self.worlds) > 1 else self.worlds[0]
            )
        if url.endswith("/world.spz"):
            if self.stream_spz:
                return httpx2.Response(200, stream=ChunkedBody([SPZ[:8], SPZ[8:]]))
            return httpx2.Response(200, content=SPZ)
        if url.endswith("/pano.png"):
            return httpx2.Response(200, content=self.pano)
        return httpx2.Response(404)


def op(done: bool, status: str, **extra: Any) -> dict:
    return {"operation_id": OP, "done": done, "error": None,
            "metadata": {"progress": {"status": status}}, **extra}  # fmt: skip


SPZ_URLS = {"500k": "https://cdn.example/world.spz"}
# Measured live 18.11.2026: the finished operation has the splats but pano_url is null.
DONE = op(True, "SUCCEEDED", response={"world_id": WID, "assets": {
    "splats": {"spz_urls": SPZ_URLS}, "imagery": {"pano_url": None},
}})  # fmt: skip
WORLD = {"world_id": WID, "assets": {
    "splats": {"spz_urls": SPZ_URLS}, "imagery": {"pano_url": "https://cdn.example/pano.png"},
}}  # fmt: skip
NO_PANO = {
    "world_id": WID,
    "assets": {"splats": {"spz_urls": SPZ_URLS}, "imagery": {"pano_url": None}},
}


def png(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(out, "PNG")
    return out.getvalue()


def client(api: Api, **extra: Any) -> WorldLabsClient:
    cfg = settings("postgresql+asyncpg://u:p@h/x", world3d_poll_s=0.001, **{**ON, **extra})
    return WorldLabsClient(
        cfg, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(api.handler))
    )


async def test_client_polls_downloads_and_keeps_the_key_off_the_cdn() -> None:
    api = Api(polls=[op(False, "IN_PROGRESS"), DONE])
    assets = await client(api).generate("A harbor.")
    assert assets.spz == SPZ
    assert Image.open(io.BytesIO(assets.panorama_webp)).format == "WEBP"
    start = api.requests[0]
    assert start.headers["WLT-Api-Key"] == "wl-key"
    assert json.loads(start.content) == {
        "display_name": "Nuvistela world",
        "model": "marble-1.0-draft",
        "permission": {"public": False},
        "world_prompt": {"type": "text", "text_prompt": "A harbor."},
    }
    assert all("WLT-Api-Key" not in r.headers for r in api.requests if "cdn.example" in str(r.url))


async def test_client_takes_the_panorama_from_the_world_when_the_operation_has_none() -> None:
    api = Api(polls=[DONE])
    assets = await client(api).generate("A harbor.")
    assert assets.spz == SPZ
    assert Image.open(io.BytesIO(assets.panorama_webp)).format == "WEBP"
    assert any(str(r.url).endswith(f"worlds/{WID}") for r in api.requests)


async def test_client_polls_the_world_until_the_panorama_appears() -> None:
    api = Api(polls=[DONE], worlds=[NO_PANO, WORLD])
    assert (await client(api).generate("A harbor.")).spz == SPZ
    assert sum(str(r.url).endswith(f"worlds/{WID}") for r in api.requests) == 2


async def test_client_accepts_the_world_wrapped_in_a_world_key() -> None:
    api = Api(polls=[DONE], worlds=[{"world": WORLD}])
    assert (await client(api).generate("A harbor.")).spz == SPZ


async def test_client_keeps_polling_while_the_splat_urls_are_missing() -> None:
    bare = {"assets": {"splats": {"spz_urls": None}, "imagery": {"pano_url": None}}}
    api = Api(polls=[DONE], worlds=[bare, WORLD])
    assert (await client(api).generate("A harbor.")).spz == SPZ
    assert sum(str(r.url).endswith(f"worlds/{WID}") for r in api.requests) == 2


@pytest.mark.parametrize("response", [{"assets": {}}, {"world_id": None}, {"world_id": ""}])
async def test_client_refuses_an_operation_without_a_world_id(response: dict) -> None:
    api = Api(polls=[op(True, "SUCCEEDED", response=response)])
    with pytest.raises(SceneError, match="no scene in the response"):
        await client(api).generate("A harbor.")
    assert not any("/worlds/" in str(r.url) for r in api.requests)


@pytest.mark.parametrize(
    ("pano", "spz"),
    [("http://cdn.example/pano.png", "https://cdn.example/world.spz"),
     ("https://cdn.example/pano.png", 123)],
)  # fmt: skip
async def test_client_refuses_a_world_url_that_is_not_https(pano: str, spz: object) -> None:
    world = {"assets": {"splats": {"spz_urls": {"500k": spz}}, "imagery": {"pano_url": pano}}}
    api = Api(polls=[DONE], worlds=[world])
    with pytest.raises(SceneError, match="no scene in the response"):
        await client(api).generate("A harbor.")
    assert not any("cdn.example" in str(r.url) for r in api.requests)


async def test_client_times_out_when_the_world_never_gets_a_panorama() -> None:
    api = Api(polls=[DONE], worlds=[NO_PANO])
    with pytest.raises(SceneError, match="Timeout"):
        await client(api, world3d_timeout_s=0.1).generate("A harbor.")


async def test_client_failed_operation_raises() -> None:
    api = Api(polls=[op(True, "FAILED", error={"code": 500})])
    with pytest.raises(SceneError, match="FAILED"):
        await client(api).generate("A harbor.")


async def test_client_timeout_raises() -> None:
    api = Api(polls=[op(False, "IN_PROGRESS")])
    with pytest.raises(SceneError, match="Timeout"):
        await client(api, world3d_timeout_s=0.05).generate("A harbor.")


async def test_client_refuses_an_unpriced_model_and_a_missing_key() -> None:
    with pytest.raises(AgentConfigError):
        client(Api(), world3d_model="marble-9")
    with pytest.raises(AgentConfigError):
        client(Api(), worldlabs_api_key=None)
    assert client(Api()).price_micro == PRICE
    assert client(Api(), world3d_model="marble-1.1").price_micro == 1580 * 800


async def test_client_takes_a_marble_1_1_panorama_at_its_real_size() -> None:
    api = Api(polls=[DONE])
    api.pano = png((4608, 2304))
    assets = await client(api, world3d_model="marble-1.1").generate("A harbor.")
    assert Image.open(io.BytesIO(assets.panorama_webp)).size == (4096, 2048)


async def test_client_refuses_a_declared_size_past_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(world3d_client, "MAX_ASSET_BYTES", len(SPZ) - 1)
    with pytest.raises(SceneError, match="asset too large"):
        await client(Api(polls=[DONE])).generate("A harbor.")


async def test_client_aborts_a_streamed_download_past_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(world3d_client, "MAX_ASSET_BYTES", len(SPZ) - 1)
    api = Api(polls=[DONE], stream_spz=True)  # no Content-Length: only the chunk count can stop it
    with pytest.raises(SceneError, match="asset too large"):
        await client(api).generate("A harbor.")
    assert not any(str(r.url).endswith("/pano.png") for r in api.requests)  # stopped on the SPZ


def test_unpriced_model_or_price_above_either_cap_disables_3d() -> None:
    url = "postgresql+asyncpg://u:p@h/x"
    assert settings(url, **ON).world3d_enabled
    assert not settings(url, **{**ON, "world3d_model": "marble-9"}).world3d_enabled
    assert not settings(url, **{**ON, "world3d_model": "marble-1.1"}).world3d_enabled  # 1.26 > 0.20
    wide = {**ON, "world3d_model": "marble-1.1", "world3d_family_daily_cap_usd": 2.0}
    assert settings(url, **wide).world3d_enabled
    assert not settings(url, **{**ON, "world3d_global_daily_cap_usd": 0.1}).world3d_enabled
    assert not settings(url, **{**ON, "worldlabs_api_key": None}).world3d_enabled
