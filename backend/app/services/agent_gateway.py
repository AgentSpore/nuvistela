"""Channel-agnostic entry to the game master: every adapter (web, Telegram) calls `handle`."""

from typing import Protocol

from app.agent.models import AgentEvent, AgentReply


class TurnRunner(Protocol):
    async def run_turn(self, event: AgentEvent) -> AgentReply: ...


class AgentGateway:
    """One inbound event in, one reply out; the adapter delivers the reply to its channel.

    Adapters resolve the sender to a member first, so `event.family_id` always comes from an
    authenticated member, never from channel input.
    """

    def __init__(self, runtime: TurnRunner) -> None:
        self._runtime = runtime

    async def handle(self, event: AgentEvent) -> AgentReply:
        return await self._runtime.run_turn(event)
