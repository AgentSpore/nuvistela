"""Money gate of the chat agent: every model request is reserved before it is sent.

One reservation per request, not per turn: the prompt grows with every tool round and its size
is only known when the request is built, so a per-turn sum could under-reserve. The (turn id,
request number) pair is the reservation key, so no migration is needed.
"""

import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.usage import RequestUsage, RunUsage
from pydantic_core import to_json
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.deps import GameDeps
from app.agent.errors import AgentBudgetExceededError, AgentUnavailableError
from app.agent.money_gate import ModelPrice, MoneyGate
from app.core.config import Settings

logger = logging.getLogger(__name__)
# Bytes the provider framing adds around the serialised messages and tool schemas.
FRAMING_OVERHEAD = 1500


def chat_price(settings: Settings) -> ModelPrice:
    return ModelPrice(settings.chat_price_in_usd_per_mtok, settings.chat_price_out_usd_per_mtok)


@dataclass(frozen=True)
class ChatSpend:
    """Reserve and settle the requests of one turn of one family against the shared gate."""

    gate: MoneyGate
    engine: AsyncEngine
    price: ModelPrice
    max_tokens: int
    family_id: UUID
    turn_id: UUID = field(default_factory=uuid4)

    def worst_case(self, request: ModelRequestContext) -> int:
        """The whole serialised prompt (a token is at least a byte) plus all `max_tokens`."""
        tools = to_json(request.model_request_parameters, fallback=repr)
        prompt = ModelMessagesTypeAdapter.dump_json(request.messages)
        return self.price.worst_case(len(prompt) + len(tools) + FRAMING_OVERHEAD, self.max_tokens)

    async def reserve(self, attempt: int, micro: int) -> bool:
        """Own transaction: the reservation must survive a rollback of the turn's transaction."""
        verdict = await self.gate.reserve(self.family_id, self.turn_id, attempt, micro)
        return verdict == "reserved"

    async def settle(self, attempt: int, usage: RequestUsage) -> None:
        actual = self.price.cost(
            RunUsage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        )
        async with self.engine.begin() as conn:
            await self.gate.settle(conn, self.turn_id, attempt, actual)


class ChatMoneyGate(AbstractCapability[GameDeps]):
    """No reservation, no model call; a request that fails keeps its reservation counted."""

    async def wrap_model_request(
        self,
        ctx: RunContext[GameDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        spend = ctx.deps.spend
        if spend is None:
            raise AgentUnavailableError("chat money gate is not wired")
        if not await spend.reserve(ctx.run_step, spend.worst_case(request_context)):
            logger.info("chat request refused: daily money cap, step=%s", ctx.run_step)
            raise AgentBudgetExceededError("daily money cap reached")
        response = await handler(request_context)
        await spend.settle(ctx.run_step, response.usage)
        return response
