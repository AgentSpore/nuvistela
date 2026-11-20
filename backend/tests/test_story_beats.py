import inspect
import json
import math
import re

import httpx2
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent.chapter_writer import (
    INSTRUCTIONS,
    ChapterOut,
    ChapterSpec,
    ChapterWriter,
    build_chapter_writer,
)
from app.core.config import Settings
from app.domain.adventure import MILESTONE_MAX, NextQuest, beat_of
from app.repositories.job_repository import JobRepository
from tests.test_chapter_worker import CHAPTER, make_settings


@pytest.mark.parametrize(
    ("number", "beat"),
    [(1, "opening"), (2, "turn"), (3, "milestone"), (4, "develop"), (5, "turn"), (6, "milestone")],
)
def test_beat_follows_the_chapter_number(number: int, beat: str) -> None:
    assert beat_of(number) == beat


def test_milestone_over_the_limit_is_rejected() -> None:
    ChapterOut.model_validate({**CHAPTER, "milestone": "x" * MILESTONE_MAX})
    with pytest.raises(ValidationError):
        ChapterOut.model_validate({**CHAPTER, "milestone": "x" * (MILESTONE_MAX + 1)})


def test_next_quest_kind_is_required_and_from_the_six() -> None:
    quest = {k: v for k, v in CHAPTER["next_quest"].items() if k != "kind"}
    for bad in (quest, {**quest, "kind": "dance"}):
        with pytest.raises(ValidationError):
            NextQuest.model_validate(bad)


@pytest.fixture
def milestone_writer(postgres_url: str):
    return build_chapter_writer(make_settings(postgres_url))


def scripted(answers: list[str | None]):
    """A model that answers with the next milestone in the list on every request."""
    asked: list[int] = []

    async def script(_messages, info) -> ModelResponse:
        asked.append(1)
        wanted = re.search(r'next_quest_kind\\*": \\*"(\w+)', str(_messages))
        quest = {**CHAPTER["next_quest"], "kind": wanted and wanted[1]}
        body = {
            **CHAPTER,
            "next_quest": quest,
            "milestone": answers[min(len(asked), len(answers)) - 1],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])

    return FunctionModel(script), asked


@pytest.mark.parametrize(
    ("number", "answers", "milestone", "requests"),
    [
        (3, ["The station got a sign"], "The station got a sign", 1),
        (3, [None, "A sign"], "A sign", 2),  # missing: asked once, then accepted
        (3, ["   ", None], None, 2),  # still missing after the retry: no failure
        (2, ["A sign"], None, 1),  # off its beat: dropped silently
        (2, [None], None, 1),
    ],
)
async def test_milestone_belongs_to_its_beat_and_never_costs_the_chapter(
    milestone_writer, number: int, answers: list[str | None], milestone: str | None, requests: int
) -> None:
    model, asked = scripted(answers)
    spec = ChapterSpec("en", "space", "w", None, "t", "d", None, ("adult",), number)
    with milestone_writer.agent.override(model=model):
        out, _ = await milestone_writer.write(spec)
    assert out.milestone == milestone and len(asked) == requests


def test_prompt_carries_the_beat_and_the_chosen_kind() -> None:
    spec = ChapterSpec(
        "en", "space", "w", None, "t", "d", None, ("adult",), 6, None, ("say", "make", "care")
    )
    prompt = ChapterWriter.prompt(spec)
    assert '"beat": "milestone"' in prompt
    assert '"next_quest_kind": "say"' in prompt  # chapter 6, last two make/care


def test_other_real_people_are_named_by_role_only() -> None:
    assert "named by role only" in INSTRUCTIONS and "never by name" in INSTRUCTIONS


def test_chapter_timeout_covers_two_requests_inside_the_job_lease() -> None:
    lease = inspect.signature(JobRepository.claim).parameters["lease"].default
    assert Settings.model_fields["chapter_timeout_s"].default == 90.0
    assert lease.total_seconds() > Settings.model_fields["chapter_timeout_s"].default


async def test_worst_case_covers_the_real_cost_of_a_milestone_retry(postgres_url: str) -> None:
    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        args = {**CHAPTER, "milestone": None if len(bodies) == 1 else "A sign"}
        call = {
            "id": "c",
            "type": "function",
            "function": {"name": "final_result", "arguments": json.dumps(args)},
        }
        message = {"role": "assistant", "content": None, "tool_calls": [call]}
        return httpx2.Response(
            200,
            json={
                "id": "r",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "provider": "p",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    settings = make_settings(postgres_url).model_copy(update={"chapter_timeout_s": 30.0})
    writer = build_chapter_writer(settings, http_client=client)
    spec = ChapterSpec("en", "space", "w", None, "t", "d", None, ("adult",), 3)
    await writer.write(spec)
    assert len(bodies) == 2
    sent = sum(
        len(json.dumps([b["messages"], b["tools"]], ensure_ascii=False).encode()) for b in bodies
    )
    real = math.ceil(sent * 0.051 + 2 * writer.max_tokens * 0.567)
    assert writer.worst_case(spec) >= real
