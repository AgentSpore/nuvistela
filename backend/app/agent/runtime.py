"""Entrypoint `run_turn`: one event in, one reply out, with limits and typed failures."""

import asyncio
from collections.abc import Callable

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from app.agent.deps import GameDeps
from app.agent.errors import AgentBudgetExceededError, AgentUnavailableError
from app.agent.models import AgentEvent, AgentReply
from app.core.config import Settings


class GameMasterRuntime:
    """Runs the game master for events; deps are built per event from its family id."""

    def __init__(
        self,
        agent: Agent[GameDeps, str],
        deps_factory: Callable[[str], GameDeps],
        settings: Settings,
    ) -> None:
        self.agent = agent
        self._deps_factory = deps_factory
        self._timeout_s = settings.agent_timeout_s
        self._limits = UsageLimits(
            request_limit=settings.agent_request_limit,
            total_tokens_limit=settings.agent_total_tokens_limit,
        )

    async def run_turn(self, event: AgentEvent) -> AgentReply:
        """Handle one event or raise AgentBudgetExceededError / AgentUnavailableError."""
        prompt = f"[{event.kind} via {event.channel}] {event.text}"
        try:
            async with asyncio.timeout(self._timeout_s):
                result = await self.agent.run(
                    prompt, deps=self._deps_factory(event.family_id), usage_limits=self._limits
                )
        except UsageLimitExceeded as exc:
            raise AgentBudgetExceededError(str(exc)) from exc
        except TimeoutError as exc:
            raise AgentUnavailableError("LLM call timed out") from exc
        except (ModelAPIError, UnexpectedModelBehavior) as exc:
            raise AgentUnavailableError("LLM call failed") from exc
        return AgentReply(text=result.output)
