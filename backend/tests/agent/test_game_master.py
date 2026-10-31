import asyncio
import dataclasses
import json

import httpx2
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.agent.errors import AgentBudgetExceededError, AgentConfigError, AgentUnavailableError
from app.agent.factory import build_game_master
from app.agent.models import AgentReply
from app.agent.runtime import GameMasterRuntime
from tests.agent.conftest import MemoryConversations


def completion(text: str) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "vendor/model-x",
        "provider": "TestProvider",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def runtime(settings, deps_factory, http_client=None, store=None) -> GameMasterRuntime:
    agent = build_game_master(settings, http_client=http_client)
    return GameMasterRuntime(agent, deps_factory, settings, store or MemoryConversations())


async def test_agent_calls_family_state_tool_with_event_family(
    make_settings, deps_factory, families, event
) -> None:
    settings = make_settings()
    rt = runtime(settings, deps_factory)
    with rt.agent.override(model=TestModel(call_tools=["get_family_state"])):
        reply = await rt.run_turn(event)
    assert families.calls == ["fam-1"]
    assert isinstance(reply, AgentReply)
    assert "The Ivanovs" in reply.text  # TestModel echoes the tool return


async def test_request_carries_configured_model_and_zdr_routing(
    make_settings, deps_factory, event
) -> None:
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=completion("Hello family"))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    reply = await runtime(make_settings(), deps_factory, client).run_turn(event)
    assert reply.text == "Hello family"
    (body,) = seen
    assert body["model"] == "vendor/model-x"
    assert body["provider"] == {"data_collection": "deny", "zdr": True}
    assert "test-key" not in json.dumps(body)


async def test_request_limit_exceeded_raises_budget_error(
    make_settings, deps_factory, event
) -> None:
    calls: list[int] = []

    def loop_forever(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart("get_family_state", {})])

    rt = runtime(make_settings(agent_request_limit=2), deps_factory)
    with rt.agent.override(model=FunctionModel(loop_forever)):
        with pytest.raises(AgentBudgetExceededError):
            await rt.run_turn(event)
    assert len(calls) == 2  # stopped by the configured limit, not the SDK default of 50


async def test_token_limit_exceeded_raises_budget_error(make_settings, deps_factory, event) -> None:
    rt = runtime(make_settings(agent_total_tokens_limit=1), deps_factory)
    with rt.agent.override(model=TestModel(call_tools=["get_family_state"])):
        with pytest.raises(AgentBudgetExceededError):
            await rt.run_turn(event)


async def test_provider_error_raises_unavailable(make_settings, deps_factory, event) -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(503, json={}))
    )
    with pytest.raises(AgentUnavailableError):
        await runtime(make_settings(), deps_factory, client).run_turn(event)


async def test_timeout_raises_unavailable(make_settings, deps_factory, event) -> None:
    never = asyncio.Event()

    async def hang(request: httpx2.Request) -> httpx2.Response:
        await never.wait()
        return httpx2.Response(200, json=completion("late"))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(hang))
    rt = runtime(make_settings(agent_timeout_s=0.05), deps_factory, client)
    with pytest.raises(AgentUnavailableError):
        await asyncio.wait_for(rt.run_turn(event), 5)  # a missing timeout fails, not hangs


@pytest.mark.parametrize("missing", ["family_llm_model", "openrouter_api_key"])
def test_missing_llm_config_is_a_typed_error(make_settings, missing) -> None:
    with pytest.raises(AgentConfigError):
        build_game_master(make_settings(**{missing: None}))


async def test_family_text_is_user_content_never_system(make_settings, deps_factory, event) -> None:
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=completion("ok"))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    await runtime(make_settings(), deps_factory, client).run_turn(event)
    by_role = {m["role"]: json.dumps(m) for m in seen[0]["messages"]}
    assert "What now?" in by_role["user"]
    assert all("What now?" not in v for k, v in by_role.items() if k != "user")


async def test_history_is_loaded_saved_and_scoped_per_family(
    make_settings, deps_factory, conversations, event
) -> None:
    sizes: list[int] = []

    def echo(messages, info):
        sizes.append(len(messages))
        return ModelResponse(parts=[TextPart("hi")])

    rt = runtime(make_settings(), deps_factory, store=conversations)
    with rt.agent.override(model=FunctionModel(echo)):
        await rt.run_turn(event)
        await rt.run_turn(event)
        await rt.run_turn(dataclasses.replace(event, family_id="fam-2"))
    assert sizes == [1, 3, 1]  # second turn sees the first; other family starts clean
    assert set(conversations.data) == {"fam-1", "fam-2"}


async def test_failed_turn_saves_nothing(make_settings, deps_factory, conversations, event) -> None:
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(503, json={}))
    )
    with pytest.raises(AgentUnavailableError):
        await runtime(make_settings(), deps_factory, client, conversations).run_turn(event)
    assert conversations.data == {}


async def test_family_daily_token_budget_is_per_family(make_settings, deps_factory, event) -> None:
    rt = runtime(make_settings(agent_family_daily_tokens=1), deps_factory)
    plain = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")]))
    with rt.agent.override(model=plain):
        await rt.run_turn(event)  # crosses the line; the next request is refused
        with pytest.raises(AgentBudgetExceededError):
            await rt.run_turn(event)
        await rt.run_turn(dataclasses.replace(event, family_id="fam-2"))
