import json
from uuid import uuid4

import httpx2
import pytest
from pydantic import SecretStr
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.agent.world_generator import WorldInvalid, build_world_generator
from app.core.config import Settings
from tests.test_world import world_args

SETTINGS = Settings(
    _env_file=None,
    database_url="postgresql+asyncpg://u:p@localhost/x",
    world_model="vendor/world-x",
    openrouter_api_key=SecretStr("test-key"),
)


def spec(ids: list[str]) -> dict:
    return {
        "genre": "space",
        "custom_genre": None,
        "locale": "ru",
        "members": [{"member_id": i, "age_band": "adult", "interests": []} for i in ids],
        "private": ["Anya"],
    }


async def test_world_request_carries_zdr_and_require_parameters() -> None:
    seen: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(500, json={"error": {"message": "stop"}})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    gen = build_world_generator(SETTINGS, http_client=client)
    with pytest.raises(Exception):  # noqa: B017, PT011 - only the outgoing request is under test
        await gen.generate(spec([str(uuid4())]))
    (body,) = seen
    assert body["model"] == "vendor/world-x"
    assert body["provider"] == {"data_collection": "deny", "zdr": True, "require_parameters": True}


async def test_duplicate_hero_for_one_member_is_rejected() -> None:
    a, b = str(uuid4()), str(uuid4())

    def script(messages, info) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, world_args([a, b, b]))])

    gen = build_world_generator(SETTINGS)
    with gen.agent.override(model=FunctionModel(script)), pytest.raises(WorldInvalid):
        await gen.generate(spec([a, b]))
