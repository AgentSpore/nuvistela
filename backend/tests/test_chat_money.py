"""The chat agent spends through the real MoneyGate: real app, real Postgres, scripted model."""

import json
from typing import Any

import httpx2
import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_core import to_json

from app.agent.chat_spend import ChatSpend, chat_price
from app.agent.factory import build_game_master
from app.core.config import Settings
from app.main import create_app
from tests.conftest import _client
from tests.test_agent_api import URL, make_member

SELECT = "SELECT * FROM llm_spend WHERE family_id = $1::uuid ORDER BY attempt"


def chat_settings(url: str, **over) -> Settings:
    return Settings(_env_file=None, database_url=url, cookie_secure=False, **over)


@pytest.fixture
async def make_client(postgres_url: str, agent, db_fetch):
    gens: list[Any] = []

    async def build(**over) -> AsyncClient:
        await db_fetch("DELETE FROM llm_spend")
        gens.append(_client(create_app(chat_settings(postgres_url, **over), agent=agent)))
        return await anext(gens[-1])

    yield build
    for gen in gens:
        await gen.aclose()


async def say(client: AsyncClient, cookie: dict, text: str = "hi"):
    return await client.post(URL, json={"text": text}, headers=cookie)


async def test_reservation_exists_before_the_model_is_called_and_is_settled(
    make_client, agent, db_fetch
) -> None:
    client = await make_client()
    cookie, fid = await make_member(client)
    during: list[list] = []

    async def model(messages, info: AgentInfo) -> ModelResponse:
        during.append(await db_fetch(SELECT, fid))
        return ModelResponse(parts=[TextPart("ok")])

    with agent.override(model=FunctionModel(model)):
        resp = await say(client, cookie)
    assert resp.status_code == 200
    (before,) = during
    assert [r["state"] for r in before] == ["reserved"] and before[0]["reserved_micro_usd"] > 0
    (row,) = await db_fetch(SELECT, fid)
    assert row["state"] == "settled" and 0 < row["actual_micro_usd"] <= row["reserved_micro_usd"]


async def test_at_the_cap_the_model_is_not_called_and_the_caller_gets_429(
    make_client, agent, db_fetch
) -> None:
    client = await make_client(llm_family_daily_cap_usd=0.000001)
    cookie, fid = await make_member(client)
    calls: list[int] = []

    def model(messages, info) -> ModelResponse:
        calls.append(1)
        return ModelResponse(parts=[TextPart("ok")])

    with agent.override(model=FunctionModel(model)):
        resp = await say(client, cookie)
    assert resp.status_code == 429 and calls == []
    assert await db_fetch(SELECT, fid) == []


async def test_global_cap_also_stops_the_call(make_client, agent, db_fetch) -> None:
    client = await make_client(llm_global_daily_cap_usd=0.000001)
    cookie, fid = await make_member(client)
    with agent.override(model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("x")]))):
        resp = await say(client, cookie)
    assert resp.status_code == 429 and await db_fetch(SELECT, fid) == []


async def test_multi_request_turn_reserves_each_request_in_full(
    make_client, agent, db_fetch
) -> None:
    client = await make_client()
    cookie, fid = await make_member(client)
    sent: list[int] = []  # bytes of what the model actually received, per request

    def model(messages, info: AgentInfo) -> ModelResponse:
        sent.append(
            len(ModelMessagesTypeAdapter.dump_json(messages))
            + len(to_json(info.function_tools, fallback=repr))
        )
        if len(sent) == 1:
            return ModelResponse(parts=[ToolCallPart("get_family_state", {})])
        return ModelResponse(parts=[TextPart("done")])

    with agent.override(model=FunctionModel(model)):
        resp = await say(client, cookie)
    assert resp.status_code == 200 and len(sent) == 2
    rows = await db_fetch(SELECT, fid)
    assert [r["attempt"] for r in rows] == [1, 2] and len({r["job_id"] for r in rows}) == 1
    price, ceiling = chat_price(chat_settings("postgresql+asyncpg://u:p@x/y")), 1500
    for row, size in zip(rows, sent, strict=True):
        assert row["state"] == "settled"
        assert row["reserved_micro_usd"] >= price.worst_case(size, ceiling)
        assert row["actual_micro_usd"] <= row["reserved_micro_usd"]
    assert rows[1]["reserved_micro_usd"] > rows[0]["reserved_micro_usd"]  # the prompt grew


async def test_failed_call_keeps_its_reservation_counted(make_client, agent, db_fetch) -> None:
    client = await make_client()
    cookie, fid = await make_member(client)

    def model(messages, info) -> ModelResponse:
        raise ModelAPIError("vendor/model-x", "boom")

    with agent.override(model=FunctionModel(model)):
        resp = await say(client, cookie)
    assert resp.status_code == 503
    (row,) = await db_fetch(SELECT, fid)
    assert row["state"] == "reserved" and row["actual_micro_usd"] is None


async def test_second_turn_after_the_cap_is_filled_is_refused(make_client, agent, db_fetch) -> None:
    client = await make_client(llm_family_daily_cap_usd=0.002)  # room for one turn, not two
    cookie, fid = await make_member(client)
    calls: list[int] = []

    async def model(messages, info) -> ModelResponse:
        calls.append(1)
        return ModelResponse(parts=[TextPart("ok")])

    await db_fetch(
        "INSERT INTO llm_spend (family_id, job_id, attempt, reserved_micro_usd)"
        " VALUES ($1::uuid, gen_random_uuid(), 1, 1500)",
        fid,
    )
    with agent.override(model=FunctionModel(model)):
        resp = await say(client, cookie)
    assert resp.status_code == 429 and calls == []


CHAT_REPLY = {
    "id": "x",
    "object": "chat.completion",
    "created": 1,
    "model": "vendor/model-x",
    "provider": "TestProvider",
}
USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


def _reply(body: dict) -> dict:
    """A tool call first, plain text once the tool result is in the request."""
    if body["messages"][-1]["role"] == "tool":
        message = {"role": "assistant", "content": "Готово"}
    else:
        call = {"name": "get_family_state", "arguments": "{}"}
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": call}],
        }
    finish = "stop" if message["content"] else "tool_calls"
    choice = {"index": 0, "finish_reason": finish, "message": message}
    return {**CHAT_REPLY, "choices": [choice], "usage": USAGE}


async def wire_run(postgres_url: str, db_fetch) -> tuple[list[int], list[int]]:
    """Two Cyrillic turns (so the second has history) through the real OpenRouterModel.

    Returns the bytes of each HTTP request body and the micro-USD reserved for it, in order.
    """
    sizes: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sizes.append(len(request.content))
        return httpx2.Response(200, json=_reply(json.loads(request.content)))

    llm = chat_settings(
        postgres_url, family_llm_model="vendor/model-x", openrouter_api_key=SecretStr("k")
    )
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(chat_settings(postgres_url), agent=build_game_master(llm, http_client=http))
    await db_fetch("DELETE FROM llm_spend")
    async for client in _client(app):
        cookie, fid = await make_member(client, "Ивановы")
        for text in ("Привет, расскажи про нашу семью", "А что нам делать сегодня вечером?"):
            assert (await say(client, cookie, text)).status_code == 200
    rows = await db_fetch(SELECT, fid)
    return sizes, [r["reserved_micro_usd"] for r in sorted(rows, key=lambda r: r["id"])]


def short_of_wire(sizes: list[int], reserved: list[int]) -> list[int]:
    price = chat_price(chat_settings("postgresql+asyncpg://u:p@x/y"))
    return [i for i, (n, r) in enumerate(zip(sizes, reserved, strict=True))
            if r < price.worst_case(n, 1500)]  # fmt: skip


async def test_reserved_bytes_cover_the_real_request_body(postgres_url, db_fetch) -> None:
    sizes, reserved = await wire_run(postgres_url, db_fetch)
    assert len(sizes) == 4  # two turns of a tool round each
    assert short_of_wire(sizes, reserved) == []


async def test_a_smaller_measure_would_be_caught_by_the_wire_test(
    postgres_url, db_fetch, monkeypatch
) -> None:
    def halved(self, request) -> int:  # mutation: no framing overhead, half the messages
        prompt = ModelMessagesTypeAdapter.dump_json(request.messages)
        return self.price.worst_case(len(prompt) // 2, self.max_tokens)

    monkeypatch.setattr(ChatSpend, "worst_case", halved)
    sizes, reserved = await wire_run(postgres_url, db_fetch)
    assert short_of_wire(sizes, reserved) != []
