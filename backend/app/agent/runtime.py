"""Entrypoint `run_turn`: one event in, one reply out, with limits and typed failures."""

from collections.abc import Callable

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from app.agent.deps import GameDeps
from app.agent.errors import AgentBudgetExceededError, AgentUnavailableError
from app.agent.models import AgentEvent, AgentReply
from app.agent.store import ConversationStore
from app.core.config import Settings


class GameMasterRuntime:
    """Runs the game master for events; deps and history are scoped to the event's family."""

    def __init__(
        self,
        agent: Agent[GameDeps, str],
        deps_factory: Callable[[str], GameDeps],
        settings: Settings,
        store: ConversationStore,
    ) -> None:
        self.agent = agent
        self._deps_factory = deps_factory
        self._store = store
        self._timeout_s = settings.agent_timeout_s
        self._limits = UsageLimits(
            request_limit=settings.agent_request_limit,
            total_tokens_limit=settings.agent_total_tokens_limit,
        )

    async def run_turn(self, event: AgentEvent) -> AgentReply:
        """Handle one event or raise AgentBudgetExceededError / AgentUnavailableError."""
        history = await self._store.load(event.family_id)
        try:
            result = await self.agent.run(
                f"[{event.kind} via {event.channel}] {event.text}",
                deps=self._deps_factory(event.family_id),
                message_history=history,
                conversation_id=f"family:{event.family_id}",
                usage_limits=self._limits,
                timeout=self._timeout_s,
            )
        except UsageLimitExceeded as exc:  # includes harness SpendLimitExceeded
            raise AgentBudgetExceededError(str(exc)) from exc
        except TimeoutError as exc:
            raise AgentUnavailableError("LLM call timed out") from exc
        except (ModelAPIError, UnexpectedModelBehavior) as exc:
            raise AgentUnavailableError("LLM call failed") from exc
        await self._store.append(event.family_id, result.new_messages())
        return AgentReply(text=result.output)
