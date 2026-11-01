"""Run the real backend app with a deterministic test model instead of OpenRouter.

Started by the e2e suite with the backend's venv. The environment is an allowlist built by
stack.py (PATH, HOME, LANG, TMPDIR, DATABASE_URL, PORT, PYTHONPATH); `.env` is never read.

Only the model is replaced: `create_app` builds the agent itself, with the real
PostgresSpendStore on its own asyncpg pool, so the per-family budget path runs for real.
"""

import os
from unittest.mock import patch

import uvicorn
from app.agent import factory
from app.core.config import Settings
from app.main import create_app
from pydantic import SecretStr
from pydantic_ai.messages import (  # ty: ignore[unresolved-import] backend-venv-only package, absent from the e2e venv
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from replies import scripted_reply


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


def main() -> None:
    settings = Settings(
        _env_file=None,
        database_url=os.environ["DATABASE_URL"],
        port=int(os.environ["PORT"]),
        cookie_secure=False,  # the suite runs over plain http
        family_llm_model="test/model",
        openrouter_api_key=SecretStr("not-a-real-key"),
    )
    # The agent factory builds its model with this name: no network call is ever made.
    with patch.object(factory, "OpenRouterModel", _scripted_model):
        uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port)


if __name__ == "__main__":
    main()
