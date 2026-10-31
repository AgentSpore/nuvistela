"""Build the game master: a pydantic-ai Agent on OpenRouter with ZDR-only routing."""

import httpx2
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.agent.deps import GameDeps
from app.agent.errors import AgentConfigError
from app.agent.tools import register_tools
from app.core.config import Settings

INSTRUCTIONS = (
    "You are the game master of a cooperative family game. Be warm and encouraging, never "
    "shame or rank anyone, keep content suitable for the youngest player, and never ask for "
    "personal data such as addresses, phones or photos. Use tools to read facts; "
    "do not invent them."
)


def build_game_master(
    settings: Settings, *, http_client: httpx2.AsyncClient | None = None
) -> Agent[GameDeps, str]:
    """Create the agent from settings; `http_client` lets tests capture the outgoing request."""
    if not settings.family_llm_model or settings.openrouter_api_key is None:
        raise AgentConfigError("FAMILY_LLM_MODEL and OPENROUTER_API_KEY must be set")
    provider = OpenRouterProvider(
        api_key=settings.openrouter_api_key.get_secret_value(), http_client=http_client
    )
    model_settings = OpenRouterModelSettings(
        openrouter_provider={"data_collection": "deny", "zdr": True},
        timeout=settings.agent_timeout_s,
        max_retries=0,  # the caller owns retries; one retry layer only
    )
    agent = Agent(
        OpenRouterModel(settings.family_llm_model, provider=provider),
        deps_type=GameDeps,
        instructions=INSTRUCTIONS,
        model_settings=model_settings,
        retries=0,
    )
    register_tools(agent)
    return agent
