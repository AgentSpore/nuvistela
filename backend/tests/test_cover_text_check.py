import io
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import httpx2
import pytest
from PIL import Image
from pydantic import SecretStr

from app.agent.cover_text_check import (
    CHECK_RESERVE_MICRO,
    CheckError,
    OpenRouterTextChecker,
    TextVerdict,
)
from app.agent.image_client import ImageError, ImageResult, OpenRouterImageClient
from app.repositories.job_repository import JobRepository
from app.services.cover_prompt import SAFETY_ENDING
from app.workers.image_worker import ImageWorker
from tests.test_cover_growth import Growth
from tests.test_cover_growth import build as build_growth
from tests.test_cover_worker import COST, Env, build, cover_row, settings

RED, GREEN = (200, 30, 30), (30, 200, 30)


def png(color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(out, "PNG")
    return out.getvalue()


@dataclass
class FakeImages:
    """The generator: pictures in order, each call recorded."""

    pictures: list[bytes | Exception]
    prompts: list[str] = field(default_factory=list)
    reserve_micro: int = 45_000

    def worst_case(self, prompt: str) -> int:
        return self.reserve_micro

    async def generate(self, prompt: str) -> ImageResult:
        self.prompts.append(prompt)
        item = self.pictures.pop(0)
        if isinstance(item, Exception):
            raise item
        return ImageResult(item, round(COST * 1_000_000))


@dataclass
class FakeChecker:
    """Answers in order; an exception is raised instead of answered."""

    answers: list[TextVerdict | Exception]
    seen: list[bytes] = field(default_factory=list)

    async def has_text(self, image: bytes) -> TextVerdict:
        self.seen.append(image)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


YES, NO = TextVerdict(True, 120), TextVerdict(False, 120)


@pytest.fixture
async def env(postgres_url: str, agent, db_fetch) -> AsyncIterator[Env]:
    async for e in build(postgres_url, agent, db_fetch):
        yield e


def paint(
    e: Env, postgres_url: str, images: FakeImages, checker: FakeChecker, **extra: Any
) -> None:
    e.image = ImageWorker(
        e.app.state.engine,
        cast("OpenRouterImageClient", images),
        settings(postgres_url, **extra),
        checker=checker,
    )


async def stored_color(e: Env, fid: str) -> tuple[int, int, int]:
    row = await cover_row(e, fid)
    assert row["status"] == "ready"
    return pixel(row["bytes"])


def pixel(data: bytes) -> tuple[int, int, int]:
    return cast(
        "tuple[int, int, int]", Image.open(io.BytesIO(data)).convert("RGB").getpixel((0, 0))
    )


def close(got: tuple[int, int, int], want: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= 12 for a, b in zip(got, want, strict=True))


async def run(
    e: Env, postgres_url: str, pictures: list[Any], answers: list[Any], **extra: Any
) -> tuple[str, FakeImages, FakeChecker]:
    images, checker = FakeImages(pictures), FakeChecker(answers)
    paint(e, postgres_url, images, checker, **extra)
    fid = await e.new_family_world()
    await e.drain_images()
    return fid, images, checker


async def test_text_on_the_first_picture_regenerates_once_and_stores_the_second(
    env: Env, postgres_url: str
) -> None:
    fid, images, checker = await run(env, postgres_url, [png(RED), png(GREEN)], [YES])
    assert len(images.prompts) == 2 and len(checker.seen) == 1
    assert close(await stored_color(env, fid), GREEN)
    assert images.prompts[1].startswith(images.prompts[0])  # the same world, a stronger ending
    assert len(images.prompts[1]) > len(images.prompts[0])
    assert SAFETY_ENDING in images.prompts[1]


async def test_no_text_stores_the_first_with_one_check_and_no_regen(
    env: Env, postgres_url: str
) -> None:
    fid, images, checker = await run(env, postgres_url, [png(RED), png(GREEN)], [NO])
    assert len(images.prompts) == 1 and len(checker.seen) == 1
    assert close(await stored_color(env, fid), RED)
    (spend,) = await env.spend()
    assert spend["actual_micro_usd"] == 33_600 + 120  # the picture plus the check


async def test_checker_error_accepts_the_first_picture(env: Env, postgres_url: str) -> None:
    fid, images, _ = await run(env, postgres_url, [png(RED), png(GREEN)], [CheckError("boom")])
    assert len(images.prompts) == 1
    assert close(await stored_color(env, fid), RED)
    (spend,) = await env.spend()
    assert spend["state"] == "settled"


async def test_text_twice_stores_the_second_and_never_regenerates_again(
    env: Env, postgres_url: str
) -> None:
    fid, images, checker = await run(
        env, postgres_url, [png(RED), png(GREEN), png(RED)], [YES, YES]
    )
    assert len(images.prompts) == 2 and len(checker.seen) == 1  # the second is not even checked
    assert close(await stored_color(env, fid), GREEN)


async def test_regen_is_paid_under_its_own_reservation_and_settled(
    env: Env, postgres_url: str
) -> None:
    await run(env, postgres_url, [png(RED), png(GREEN)], [YES])
    rows = await env.spend()
    assert len(rows) == 2
    assert all(r["state"] == "settled" for r in rows)
    assert sorted(r["actual_micro_usd"] for r in rows) == [33_600, 33_600 + 120]


async def test_failed_regen_keeps_the_first_picture(env: Env, postgres_url: str) -> None:
    fid, images, _ = await run(env, postgres_url, [png(RED), ImageError("HTTP 500")], [YES])
    assert len(images.prompts) == 2
    assert close(await stored_color(env, fid), RED)


async def test_over_the_cap_the_regen_is_skipped(postgres_url: str, agent, db_fetch) -> None:
    # room for the first picture's reserve (0.047) but not a second one
    async for e in build(postgres_url, agent, db_fetch, image_family_daily_cap_usd=0.08):
        fid, images, _ = await run(
            e, postgres_url, [png(RED), png(GREEN)], [YES], image_family_daily_cap_usd=0.08
        )
        assert len(images.prompts) == 1
        assert close(await stored_color(e, fid), RED)


async def test_checker_error_after_a_billed_answer_is_still_charged(
    env: Env, postgres_url: str
) -> None:
    await run(env, postgres_url, [png(RED)], [CheckError("neither", 777)])
    (spend,) = await env.spend()
    assert spend["actual_micro_usd"] == 33_600 + 777


async def test_checker_crash_keeps_the_first_picture_and_finishes_the_job(
    env: Env, postgres_url: str
) -> None:
    fid, images, _ = await run(env, postgres_url, [png(RED), png(GREEN)], [RuntimeError("bug")])
    assert len(images.prompts) == 1
    assert close(await stored_color(env, fid), RED)
    assert (await env.jobs("image"))[0]["status"] == "done"


async def test_text_regeneration_leaves_room_for_the_growth_cover_under_the_default_cap(
    postgres_url: str, agent, db_fetch
) -> None:
    """First cover with writing (picture + check + regeneration) and a growth cover, one UTC day."""
    async for g in build_growth(postgres_url, agent, db_fetch):
        await g.begin()
        (job,) = await g.db_fetch("SELECT job_id FROM worlds WHERE family_id = $1", UUID(g.fid))
        await g.db_fetch(
            "INSERT INTO world_images (family_id, world_job_id, kind, prompt, status)"
            " VALUES ($1, $2, 'cover', 'first cover', 'pending')",
            UUID(g.fid),
            job["job_id"],
        )
        async with g.worker._engine.begin() as conn:
            await JobRepository(conn).enqueue(
                "image", UUID(g.fid), {"world_job_id": str(job["job_id"])}
            )
        images = FakeImages([png(RED), png(GREEN), png(RED)], reserve_micro=47_060)
        checker = FakeChecker([YES, NO])
        g.image = ImageWorker(
            g.worker._engine, cast("OpenRouterImageClient", images), settings(postgres_url),
            checker=checker,
        )  # fmt: skip
        await g.advance(5)  # chapter 6 orders the growth cover
        while await g.image.run_once():
            pass
        assert len(images.prompts) == 3  # world cover, its regeneration, the growth cover
        assert [(r["milestone_no"], r["status"]) for r in await g.images()] == [
            (0, "ready"),
            (2, "ready"),
        ]


async def test_growth_cover_is_screened_too(postgres_url: str, agent, db_fetch) -> None:
    async for g in build_growth(postgres_url, agent, db_fetch):
        assert isinstance(g, Growth)
        await g.begin()
        await g.advance(5)  # chapter 6: milestone 2 orders the growth cover
        images, checker = FakeImages([png(RED), png(GREEN)]), FakeChecker([YES])
        g.image = ImageWorker(
            g.worker._engine,
            cast("OpenRouterImageClient", images),
            settings(postgres_url),
            checker=checker,
        )
        while await g.image.run_once():
            pass
        assert len(images.prompts) == 2 and len(checker.seen) == 1
        (row,) = await g.db_fetch(
            "SELECT bytes FROM world_images WHERE family_id = $1 AND milestone_no = 2",
            UUID(g.fid),
        )
        assert close(pixel(row["bytes"]), GREEN)


def reply(content: str | None, status: int = 200, cost: float | None = 0.0001) -> httpx2.Response:
    message = {} if content is None else {"content": content}
    body: dict[str, Any] = {"choices": [{"message": message}]}
    if cost is not None:
        body["usage"] = {"cost": cost}
    return httpx2.Response(status, json=body)


def checker_for(answer: httpx2.Response, sent: list[dict]) -> OpenRouterTextChecker:
    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return answer

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    cfg = settings("postgresql://x", openrouter_api_key=SecretStr("k"))
    return OpenRouterTextChecker(cfg, http_client=http)


@pytest.mark.parametrize(
    ("content", "has_text"), [("YES", True), (" no.\n", False), ("Yes!", True)]
)
async def test_checker_parses_a_one_word_answer_and_the_price(content: str, has_text: bool) -> None:
    sent: list[dict] = []
    verdict = await checker_for(reply(content), sent).has_text(b"webp")
    assert verdict == TextVerdict(has_text, 100)
    (body,) = sent
    assert body["provider"]["zdr"] is True and body["max_tokens"] <= 16
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/webp;")


@pytest.mark.parametrize(
    "answer",
    [reply("maybe"), reply(None), reply("YES", status=500), reply("")],
    ids=["unclear", "no-content", "http-500", "empty"],
)
async def test_checker_refuses_anything_but_a_clear_answer(answer: httpx2.Response) -> None:
    with pytest.raises(CheckError):
        await checker_for(answer, []).has_text(b"webp")


async def test_checker_without_a_reported_price_says_so() -> None:
    verdict = await checker_for(reply("NO", cost=None), []).has_text(b"webp")
    assert verdict == TextVerdict(False, None)


@pytest.mark.parametrize(
    ("answer", "charged"),
    [
        (reply("maybe"), 100),
        (reply("maybe", cost=None), CHECK_RESERVE_MICRO),
        (reply(None), 100),
        (reply("YES", status=500), None),
    ],
    ids=["unclear-priced", "unclear-unpriced", "no-content", "http-500-free"],
)
async def test_a_failed_check_carries_what_was_billed(
    answer: httpx2.Response, charged: int | None
) -> None:
    with pytest.raises(CheckError) as caught:
        await checker_for(answer, []).has_text(b"webp")
    assert caught.value.cost_micro == charged
