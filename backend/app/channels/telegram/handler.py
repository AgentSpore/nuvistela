"""Turns one Telegram update into a link, a game master turn, or nothing."""

import logging
import re

from aiogram.types import Message, Update
from starlette.datastructures import State

from app.agent.errors import AgentBudgetExceededError, AgentBusyError, AgentUnavailableError
from app.agent.models import AgentEvent
from app.channels.telegram.sender import BotIdentity, TelegramSender
from app.repositories.link_repository import LinkRepository
from app.services.gateway_factory import build_agent_gateway
from app.services.telegram_link import TelegramLinkService

logger = logging.getLogger(__name__)

LINKED = "connected"
BAD_CODE = "code invalid or expired"
NOT_ADMIN = "only chat admins can link"
EMPTY_QUESTION = "напиши вопрос после /ask"
BUSY = "wait, I'm still answering"
LIMIT = "daily limit reached"
DOWN = "game master unavailable"
MAX_MESSAGE_CHARS = 4096  # https://core.telegram.org/bots/api#sendmessage
_ADMIN_STATUSES = ("creator", "administrator")
_AGENT_REPLIES: tuple[tuple[type[Exception], str], ...] = (
    (AgentBusyError, BUSY),
    (AgentBudgetExceededError, LIMIT),
    (AgentUnavailableError, DOWN),
)


class TelegramHandler:
    """`state` is the app state: engine, agent and settings; each update opens its own transaction.

    A group message reaches the agent only as a reply to the bot, `/ask`, or an exact `@bot`
    mention entity: with Telegram privacy mode on, nothing else is delivered. A Telegram user is
    not mapped to a member yet (K-stage item): events carry `member_id=None`.
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
        command, _, rest = message.text.partition(" ")
        name, _, target = command.partition("@") if command.startswith("/") else ("", "", "")
        if target and target.lower() != bot.username.lower():
            return  # a command for another bot
        name = name.lower()
        if name == "/link":
            await self._link(message, rest.strip())
        elif name == "/ask":
            await self._chat(message, rest.strip(), bot)
        else:
            text = self._addressed_text(message, bot)
            if text is not None:
                await self._chat(message, text, bot)

    @staticmethod
    def _addressed_text(message: Message, bot: BotIdentity) -> str | None:
        """Text without the bot mention if the message is for the bot, else None."""
        text = message.text or ""
        mention = f"@{bot.username}".lower()
        mentioned = any(
            e.type == "mention" and e.extract_from(text).lower() == mention
            for e in message.entities or ()
        )
        replied = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == bot.id
        )
        if not (mentioned or replied or message.chat.type == "private"):
            return None
        if mentioned:
            text = re.sub(rf"{re.escape(mention)}\b", "", text, flags=re.IGNORECASE)
        return text.strip()

    async def _link(self, message: Message, code: str) -> None:
        if message.chat.type != "private" and not await self._is_admin(message):
            await self._reply(message, NOT_ADMIN)
            return
        async with self._state.engine.begin() as conn:
            ok = await TelegramLinkService(LinkRepository(conn)).link_chat(message.chat.id, code)
        await self._reply(message, LINKED if ok else BAD_CODE)

    async def _is_admin(self, message: Message) -> bool:
        user = message.from_user
        status = await self._sender.chat_member_status(message.chat.id, user.id if user else 0)
        return status in _ADMIN_STATUSES

    async def _chat(self, message: Message, text: str, bot: BotIdentity) -> None:
        if not text:
            await self._reply(message, EMPTY_QUESTION)
            return
        limit = self._state.settings.agent_max_text_chars
        if len(text) > limit:
            await self._reply(message, f"message too long (max {limit} characters)")
            return
        # Agent errors leave the `with` first: the turn's transaction rolls back, then we answer.
        try:
            reply = await self._turn(message, text, bot)
        except (AgentBusyError, AgentBudgetExceededError, AgentUnavailableError) as exc:
            reply = next(r for t, r in _AGENT_REPLIES if isinstance(exc, t))
            logger.info("telegram turn refused: %s chat_id=%s", type(exc).__name__, message.chat.id)
        await self._reply(message, reply)

    async def _turn(self, message: Message, text: str, bot: BotIdentity) -> str:
        async with self._state.engine.begin() as conn:
            family_id = await LinkRepository(conn).family_of_chat(message.chat.id)
            if family_id is None:
                return self._unlinked_hint(message, bot)
            event = AgentEvent(
                family_id=str(family_id), channel="telegram", kind="message", text=text
            )
            return (await build_agent_gateway(self._state, conn).handle(event)).text

    @staticmethod
    def _unlinked_hint(message: Message, bot: BotIdentity) -> str:
        command = "/link" if message.chat.type == "private" else f"/link@{bot.username}"
        return f"link this chat first: {command} <code> from the site"

    async def _reply(self, message: Message, text: str) -> None:
        for i in range(0, len(text), MAX_MESSAGE_CHARS):
            reply_to = message.message_id if i == 0 else None
            await self._sender.send(message.chat.id, text[i : i + MAX_MESSAGE_CHARS], reply_to)
