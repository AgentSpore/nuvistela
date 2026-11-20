"""Run the real backend app with a deterministic test model instead of OpenRouter.

Started by the e2e suite with the backend's venv. The environment is an allowlist built by
stack.py (PATH, HOME, LANG, TMPDIR, DATABASE_URL, PORT, PYTHONPATH); `.env` is never read.

Only the model is replaced: `create_app` builds the agent itself, with the real
PostgresSpendStore on its own asyncpg pool, so the per-family budget path runs for real.
"""

import os
import re
from unittest.mock import patch

import uvicorn
from app.agent import factory, world_generator
from app.core.config import Settings
from app.main import create_app
from pydantic import SecretStr
from pydantic_ai.messages import (  # ty: ignore[unresolved-import] backend-venv-only package, absent from the e2e venv
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # ty: ignore[unresolved-import] backend-venv-only package, absent from the e2e venv

from replies import (
    WORLD_GENRE,
    WORLD_QUEST_DESCRIPTION,
    WORLD_QUEST_REACTION,
    WORLD_QUEST_TITLE,
    WORLD_TITLE,
    scripted_reply,
)


def _last_user_text(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart):
                    return part.content if isinstance(part.content, str) else ""
    return ""


def _scripted(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(scripted_reply(_last_user_text(messages)))])


def _scripted_model(_name: str, **_kwargs: object) -> FunctionModel:
    return FunctionModel(_scripted)


def _world_args(member_ids: list[str]) -> dict:
    return {
        "title": WORLD_TITLE,
        "setting": "Бухта, где ветер носит письма",
        "tone": "тёплый",
        "locations": [
            {"name": f"Место {i}", "description": f"Светлое место номер {i}"} for i in range(4)
        ],
        "heroes": [
            {
                "member_id": m,
                "hero_class": "Искра затеи",
                "trait": "смелость",
                "skill": "забота",
            }
            for m in member_ids
        ],
        "prologue": "Бухта проснулась и ждёт вас.",
        "first_quest": {
            "title": WORLD_QUEST_TITLE,
            "description": WORLD_QUEST_DESCRIPTION,
            "skill": "забота",
            "reaction": WORLD_QUEST_REACTION,
            "kind": "make",
        },
    }


def _scripted_world(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """A valid world for WORLD_GENRE; plain text (an invalid world, then the fallback) otherwise."""
    prompt = _last_user_text(messages)
    if f'"genre": "{WORLD_GENRE}"' not in prompt:
        return _scripted(messages, info)
    ids = re.findall(r'"member_id": "([0-9a-f-]{36})"', prompt)
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, _world_args(ids))])


def _scripted_world_model(_name: str, **_kwargs: object) -> FunctionModel:
    return FunctionModel(_scripted_world)


def main() -> None:
    settings = Settings(
        _env_file=None,
        database_url=os.environ["DATABASE_URL"],
        port=int(os.environ["PORT"]),
        cookie_secure=False,  # the suite runs over plain http
        family_llm_model="test/model",
        world_max_attempts=1,  # a scripted refusal: the fallback follows at once
        openrouter_api_key=SecretStr("not-a-real-key"),
        share_token_key=SecretStr("e2e-share-token-key-" + "k" * 16),
    )
    # Each agent factory builds its model with this name: no network call is ever made.
    with (
        patch.object(factory, "OpenRouterModel", _scripted_model),
        patch.object(world_generator, "OpenRouterModel", _scripted_world_model),
    ):
        uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port)


if __name__ == "__main__":
    main()
