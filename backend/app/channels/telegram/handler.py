"""Turns one Telegram update into a link, a game master turn, or nothing."""

import logging

from aiogram.types import Message, Update
from starlette.datastructures import State

from app.agent.errors import AgentBudgetExceededError, AgentBusyError, AgentUnavailableError
from app.agent.models import AgentEvent
from app.api.v1.deps import build_agent_gateway
from app.channels.telegram.sender import BotIdentity, TelegramSender
from app.repositories.link_repository import LinkRepository
from app.services.telegram_link import TelegramLinkService

logger = logging.getLogger(__name__)

LINKED = "connected"
BAD_CODE = "code invalid or expired"
UNLINKED = "link this chat first: /link <code> from the site"
BUSY = "wait, I'm still answering"
LIMIT = "daily limit reached"
DOWN = "game master unavailable"
_AGENT_REPLIES: tuple[tuple[type[Exception], str], ...] = (
    (AgentBusyError, BUSY),
    (AgentBudgetExceededError, LIMIT),
    (AgentUnavailableError, DOWN),
)


class TelegramHandler:
    """`state` is the app state: engine, agent and settings; each update opens its own transaction.

    A Telegram user is not mapped to a member yet (K-stage item): events carry `member_id=None`.
    """

    def __init__(self, state: State, sender: TelegramSender) -> None:
        self._state = state
        self._sender = sender

    async def process(self, update: Update) -> None:
        message = update.message
        if message is None or not message.text or message.from_user is None:
            return
        if message.from_user.is_bot:
            return
        bot = await self._sender.me()
        command, _, arg = message.text.partition(" ")
        if command.split("@")[0] == "/link":
            await self._link(message, arg)
            return
        text = self._addressed_text(message, bot)
        if text is not None:
            await self._chat(message, text)

    @staticmethod
    def _addressed_text(message: Message, bot: BotIdentity) -> str | None:
        """Text without the bot mention if the message is for the bot, else None."""
        mention = f"@{bot.username}".lower()
        text = message.text or ""
        mentioned = mention in text.lower()
        replied = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == bot.id
        )
        if not (mentioned or replied or message.chat.type == "private"):
            return None
        if mentioned:
            text = " ".join(w for w in text.split() if w.lower() != mention)
        return text.strip()

    async def _link(self, message: Message, code: str) -> None:
        async with self._state.engine.begin() as conn:
            ok = await TelegramLinkService(LinkRepository(conn)).link_chat(message.chat.id, code)
        await self._reply(message, LINKED if ok else BAD_CODE)

    async def _chat(self, message: Message, text: str) -> None:
        limit = self._state.settings.agent_max_text_chars
        if len(text) > limit:
            await self._reply(message, f"message too long (max {limit} characters)")
            return
        # Agent errors leave the `with` first: the turn's transaction rolls back, then we answer.
        try:
            reply = await self._turn(message.chat.id, text)
        except (AgentBusyError, AgentBudgetExceededError, AgentUnavailableError) as exc:
            reply = next(r for t, r in _AGENT_REPLIES if isinstance(exc, t))
            logger.info("telegram turn refused: %s chat_id=%s", type(exc).__name__, message.chat.id)
        await self._reply(message, reply)

    async def _turn(self, chat_id: int, text: str) -> str:
        async with self._state.engine.begin() as conn:
            family_id = await LinkRepository(conn).family_of_chat(chat_id)
            if family_id is None:
                return UNLINKED
            event = AgentEvent(
                family_id=str(family_id), channel="telegram", kind="message", text=text
            )
            return (await build_agent_gateway(self._state, conn).handle(event)).text

    async def _reply(self, message: Message, text: str) -> None:
        await self._sender.send(message.chat.id, text, reply_to=message.message_id)
