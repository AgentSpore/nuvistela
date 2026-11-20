import json

import httpx2
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent.chapter_writer import INSTRUCTIONS, ChapterSpec, ChapterWriter, build_chapter_writer
from app.domain.adventure import QUEST_KINDS, next_quest_kind
from tests.test_chapter_worker import CHAPTER, make_settings


@pytest.mark.parametrize("recent", [(), ("say",), ("say", "make"), ("find", "gift", "move")])
@pytest.mark.parametrize("number", range(1, 13))
def test_next_kind_is_never_one_of_the_last_two(recent: tuple[str, ...], number: int) -> None:
    assert next_quest_kind(recent, number) not in recent[-2:]


def test_next_kind_rotates_with_the_chapter_number_and_is_deterministic() -> None:
    picks = [next_quest_kind((), n) for n in range(1, 7)]
    assert picks == [next_quest_kind((), n) for n in range(1, 7)]
    assert set(picks) == set(QUEST_KINDS)
    # with history: start at the chapter's slot, step forward past the banned kinds
    assert next_quest_kind(("make", "move"), 2) == "care"
    assert next_quest_kind(("say", "make"), 7) == "move"


def test_a_story_built_from_the_choices_uses_every_kind_and_keeps_windows_varied() -> None:
    kinds: list[str] = []
    for number in range(1, 40):
        kinds.append(next_quest_kind(tuple(kinds[-3:]), number))
    assert set(kinds) == set(QUEST_KINDS)
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False))
    assert all(len(set(kinds[i : i + 3])) == 3 for i in range(len(kinds) - 2))


def test_no_kind_is_closed_to_any_audience() -> None:
    # The age and safety limits are in the quest text rules; none bans a whole kind.
    assert {next_quest_kind((), n) for n in range(1, 7)} == set(QUEST_KINDS)


def test_prompt_carries_the_chosen_kind() -> None:
    spec = ChapterSpec("en", "g", "w", None, "t", "d", None, ("3-5",), 4, None, ("say", "make"))
    assert f'"next_quest_kind": "{next_quest_kind(("say", "make"), 4)}"' in ChapterWriter.prompt(
        spec
    )


def scripted(kinds: list[str]):
    asked: list[str] = []

    async def script(_messages, info) -> ModelResponse:
        kind = kinds[min(len(asked), len(kinds) - 1)]
        asked.append(kind)
        body = {**CHAPTER, "next_quest": {**CHAPTER["next_quest"], "kind": kind}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    return FunctionModel(script), asked


def test_water_place_and_food_rules_sit_inside_the_three_to_five_clause() -> None:
    start = INSTRUCTIONS.index("When a member aged 3-5 plays:")
    clause = INSTRUCTIONS[start : INSTRUCTIONS.index(". ", start)]  # up to the clause's period
    for rule in (
        "no water (stream, river, puddle, pond, bath, sea) in any kind",
        "a quest that leaves the home says in its text that an adult goes along",
        "no small objects or food that fit in a mouth (nuts, candy, coins, beads, pebbles, "
        "buttons)",
    ):
        assert rule in clause


def test_move_kind_needs_an_adult_outdoors_when_a_child_plays() -> None:
    assert "outdoors with an adult in the text when a child plays" in INSTRUCTIONS


@pytest.mark.parametrize(
    ("answers", "requests"),
    [(["find"], 1), (["say"], 1)],  # chapter 4 wants find; a deviation is accepted, no retry
)
async def test_quest_kind_never_spends_the_retry(
    postgres_url: str, answers: list[str], requests: int
) -> None:
    writer = build_chapter_writer(make_settings(postgres_url))
    model, asked = scripted(answers)
    spec = ChapterSpec("en", "space", "w", None, "t", "d", None, ("adult",), 4)
    with writer.agent.override(model=model):
        out, _ = await writer.write(spec)
    assert out.next_quest.kind == answers[0] and len(asked) == requests


@pytest.mark.parametrize(
    ("bands", "reasoning", "max_tokens"),
    [
        (("3-5",), {"effort": "low"}, 8000),
        (("adult", "3-5"), {"effort": "low"}, 8000),
        (("adult",), {"enabled": False}, 5500),
        (("6-9", "10-13"), {"enabled": False}, 5500),
    ],
)
async def test_reasoning_and_ceiling_follow_the_youngest_audience(
    postgres_url: str, bands: tuple[str, ...], reasoning: dict, max_tokens: int
) -> None:
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(500, json={"error": {"message": "stop"}})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    writer = build_chapter_writer(make_settings(postgres_url), http_client=client)
    spec = ChapterSpec("en", "space", "w", None, "t", "d", None, bands, 1)
    with pytest.raises(Exception):  # noqa: B017, PT011 (the 500 reply only stops the call)
        await writer.write(spec)
    assert seen[0]["reasoning"] == reasoning and seen[0]["max_tokens"] == max_tokens
    assert writer.max_tokens_for(spec) == max_tokens


def test_reservation_uses_the_ceiling_of_the_call_actually_made(postgres_url: str) -> None:
    writer = build_chapter_writer(make_settings(postgres_url))
    child = ChapterSpec("en", "space", "w", None, "t", "d", None, ("3-5",), 1)
    adult = ChapterSpec("en", "space", "w", None, "t", "d", None, ("adult",), 1)
    assert writer.worst_case(child) > writer.worst_case(adult)
