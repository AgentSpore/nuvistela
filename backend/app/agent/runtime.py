"""Entrypoint `run_turn`: one event in, one reply out, with limits and typed failures."""

import dataclasses
import logging
from collections.abc import Callable

from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.usage import UsageLimits

from app.agent.deps import GameDeps
from app.agent.errors import AgentBudgetExceededError, AgentUnavailableError
from app.agent.models import AgentEvent, AgentReply
from app.agent.store import ConversationStore
from app.core.config import Settings

logger = logging.getLogger(__name__)


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
        self._history_limit = settings.agent_history_limit
        self._limits = UsageLimits(
            request_limit=settings.agent_request_limit,
            total_tokens_limit=settings.agent_total_tokens_limit,
        )

    @staticmethod
    def window(history: list[ModelMessage]) -> list[ModelMessage]:
        """Drop leading messages until the history starts at a user prompt.

        A tail slice can begin with a tool result or a model reply whose request was cut off;
        providers reject such histories, so the window always starts on a user turn.
        """
        for i, message in enumerate(history):
            is_user_turn = isinstance(message, ModelRequest) and any(
                isinstance(p, UserPromptPart) for p in message.parts
            )
            if is_user_turn:
                return history[i:]
        return []

    @staticmethod
    def _log_failure(exc: Exception) -> None:
        """Class and HTTP status only: provider bodies and keys never reach the log."""
        status = exc.status_code if isinstance(exc, ModelHTTPError) else None
        logger.warning("agent turn failed: %s status=%s", type(exc).__name__, status)

    async def run_turn(self, event: AgentEvent) -> AgentReply:
        """Handle one event or raise AgentBudgetExceededError / AgentUnavailableError."""
        history = self.window(await self._store.load(event.family_id, self._history_limit))
        try:
            result = await self.agent.run(
                event.text,
                deps=dataclasses.replace(
                    self._deps_factory(event.family_id), channel=event.channel, kind=event.kind
                ),
                message_history=history,
                conversation_id=f"family:{event.family_id}",
                usage_limits=self._limits,
                timeout=self._timeout_s,
            )
        except UsageLimitExceeded as exc:  # includes harness SpendLimitExceeded
            self._log_failure(exc)
            raise AgentBudgetExceededError(str(exc)) from exc
        except TimeoutError as exc:
            self._log_failure(exc)
            raise AgentUnavailableError("LLM call timed out") from exc
        except (ModelAPIError, UnexpectedModelBehavior) as exc:
            self._log_failure(exc)
            raise AgentUnavailableError("LLM call failed") from exc
        await self._store.append(event, result.new_messages())
        return AgentReply(text=result.output)
