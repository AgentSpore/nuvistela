"""Chapter length by the youngest readers: a 6-9 child must be able to read a whole chapter."""

import json

import pytest

from app.agent.chapter_writer import (
    INSTRUCTIONS,
    ChapterSpec,
    ChapterWriter,
    chapter_length,
    count_words,
)
from tests.test_chapter_polish import chapter, run


def spec(*bands: str) -> ChapterSpec:
    return ChapterSpec("ru", "space", "w", None, "t", "d", None, bands, 2)


def words(n: int) -> str:
    return " ".join(["слово"] * (n - 1)) + " конец."


@pytest.mark.parametrize(
    ("bands", "low", "high", "young"),
    [
        (("adult", "6-9"), 90, 160, True),
        (("3-5",), 90, 160, True),
        (("adult",), 150, 260, False),
        (("10-13", "adult", "14-17"), 150, 260, False),
        ((), 150, 260, False),
    ],
)
def test_the_youngest_reader_decides_the_length(bands, low, high, young) -> None:
    length = chapter_length(bands)
    assert (length.low, length.high, length.young) == (low, high, young)


def test_the_prompt_carries_the_range_of_the_family() -> None:
    data = json.loads(ChapterWriter.prompt(spec("adult", "6-9")).removeprefix("<story_data>")[:-13])
    assert data["chapter_words"] == "90-160" and data["young_readers"] is True
    grown = json.loads(ChapterWriter.prompt(spec("adult")).removeprefix("<story_data>")[:-13])
    assert grown["chapter_words"] == "150-260" and grown["young_readers"] is False


def test_the_instructions_follow_the_data_not_a_fixed_length() -> None:
    assert "200 to 350" not in INSTRUCTIONS
    assert "chapter_words" in INSTRUCTIONS and "young_readers" in INSTRUCTIONS
    assert "one to three short sentences" in INSTRUCTIONS
    assert "at most two short sentences" in INSTRUCTIONS
    assert "two to four sentences each unless young_readers is true" in INSTRUCTIONS


@pytest.mark.parametrize(
    ("text", "n"),
    [("The crew found it.", 4), ("Тихо светилась лампа.", 3), ("灯亮了，门开了。", 3), ("", 0)],
)
def test_words_are_counted_in_every_script(text: str, n: int) -> None:
    assert count_words(text) == n


async def test_a_chapter_too_long_for_a_child_is_retried() -> None:
    long, short = chapter(body=words(241)), chapter(body=words(120))
    out, requests = await run(long, short, spec=spec("adult", "6-9"))
    assert count_words(out.body) == 120 and requests == 2


async def test_a_chapter_too_long_twice_is_accepted_on_the_retry() -> None:
    out, requests = await run(chapter(body=words(241)), chapter(body=words(300)), spec=spec("6-9"))
    assert count_words(out.body) == 300 and requests == 2


async def test_the_child_limit_keeps_its_margin() -> None:
    out, requests = await run(chapter(body=words(240)), spec=spec("3-5"))
    assert count_words(out.body) == 240 and requests == 1


async def test_adults_get_the_longer_range() -> None:
    out, requests = await run(chapter(body=words(390)), spec=spec("adult"))
    assert requests == 1
    _, requests = await run(chapter(body=words(391)), chapter(body=words(200)), spec=spec("adult"))
    assert requests == 2


async def test_a_chapter_too_short_for_a_child_is_retried() -> None:
    short, fine = chapter(body=words(60)), chapter(body=words(120))
    out, requests = await run(short, fine, spec=spec("6-9"))
    assert count_words(out.body) == 120 and requests == 2


async def test_a_chapter_too_short_twice_is_accepted_on_the_retry() -> None:
    out, requests = await run(chapter(body=words(40)), chapter(body=words(50)), spec=spec("6-9"))
    assert count_words(out.body) == 50 and requests == 2


async def test_the_child_floor_keeps_its_margin() -> None:
    out, requests = await run(chapter(body=words(61)), spec=spec("3-5"))
    assert count_words(out.body) == 61 and requests == 1
    out, requests = await run(chapter(body=words(95)), spec=spec("6-9"))
    assert count_words(out.body) == 95 and requests == 1


async def test_adults_have_a_floor_too() -> None:
    _, requests = await run(chapter(body=words(100)), chapter(body=words(200)), spec=spec("adult"))
    assert requests == 2
    _, requests = await run(chapter(body=words(101)), spec=spec("adult"))
    assert requests == 1


async def test_a_cjk_body_above_the_floor_is_accepted() -> None:
    body = "灯" * 129 + "。"  # 130 characters count as 65 words: young floor is 60
    out, requests = await run(chapter(body=body), spec=spec("6-9"))
    assert out.body == body and requests == 1


async def test_the_floor_refusal_is_logged_without_text(caplog) -> None:
    with caplog.at_level("INFO", logger="app.agent.chapter_writer"):
        await run(chapter(body=words(60)), chapter(body=words(120)), spec=spec("6-9"))
    assert "words=60 range=90-160 retry=0" in caplog.text and "слово" not in caplog.text
