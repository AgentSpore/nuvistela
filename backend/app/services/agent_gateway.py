"""Channel-agnostic entry to the game master: every adapter (web, Telegram) calls `handle`."""

from typing import Protocol

from app.agent.models import AgentEvent, AgentReply


class TurnRunner(Protocol):
    async def run_turn(self, event: AgentEvent) -> AgentReply: ...


class AgentGateway:
    """One inbound event in, one reply out; the adapter delivers the reply to its channel.

    `event.family_id` comes from an authenticated member or from a linked channel binding (a
    Telegram chat bound to a family), never from message text. `member_id` is None for events
    from channel users who are not mapped to a member yet.
    """

    def __init__(self, runtime: TurnRunner) -> None:
        self._runtime = runtime

    async def handle(self, event: AgentEvent) -> AgentReply:
        return await self._runtime.run_turn(event)
