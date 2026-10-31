"""Run the real backend app with a deterministic test model instead of OpenRouter.

Started by the e2e suite with the backend's venv. Settings come from env vars only
(DATABASE_URL, PORT); `.env` is never read.
"""

import os

import uvicorn
from app.agent.factory import build_game_master
from app.core.config import Settings
from app.main import create_app
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from replies import REPLY


def _scripted(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(REPLY)])


def main() -> None:
    settings = Settings(
        _env_file=None,
        database_url=os.environ["DATABASE_URL"],
        port=int(os.environ["PORT"]),
        cookie_secure=False,  # the suite runs over plain http
        family_llm_model="test/model",
        openrouter_api_key=SecretStr("not-a-real-key"),
    )
    agent = build_game_master(settings)
    # The override stays active for the life of this process: no network call is ever made.
    with agent.override(model=FunctionModel(_scripted)):
        uvicorn.run(
            create_app(settings, agent=agent), host="127.0.0.1", port=settings.port
        )


if __name__ == "__main__":
    main()
