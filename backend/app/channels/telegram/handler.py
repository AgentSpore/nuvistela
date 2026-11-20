"""Turns one Telegram update into a link, a game master turn, or nothing."""

import logging
import re
from uuid import UUID

from aiogram.exceptions import AiogramError
from aiogram.types import Message, Update
from starlette.datastructures import State

from app.agent.errors import AgentBudgetExceededError, AgentBusyError, AgentUnavailableError
from app.agent.models import AgentEvent
from app.channels.telegram.sender import BotIdentity, TelegramSender
from app.channels.telegram.texts import (
    locale_from_language_code,
    localized,
    notify_changed,
    notify_status,
)
from app.repositories.link_repository import LinkRepository
from app.services.gateway_factory import build_agent_gateway
from app.services.telegram_link import TelegramLinkService

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4096  # https://core.telegram.org/bots/api#sendmessage
_ADMIN_STATUSES = ("creator", "administrator")
_AGENT_REPLIES: tuple[tuple[type[Exception], str], ...] = (
    (AgentBusyError, "busy"),
    (AgentBudgetExceededError, "limit"),
    (AgentUnavailableError, "down"),
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
        command, rest = (message.text.split(maxsplit=1) + [""])[:2]
        name, _, target = command.partition("@") if command.startswith("/") else ("", "", "")
        if target and target.lower() != bot.username.lower():
            return  # a command for another bot
        name = name.lower()
        if name == "/link":
            await self._link(message, rest.strip(), message.from_user.id)
        elif name == "/notify":
            await self._notify(message, rest.strip().lower(), message.from_user.id, bot)
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

    async def _admin_allowed(self, message: Message, user_id: int) -> bool:
        """Private chats pass; in a group only its admins do. Replies when refusing."""
        if message.chat.type == "private":
            return True
        try:
            status = await self._sender.chat_member_status(message.chat.id, user_id)
        except AiogramError as exc:
            logger.warning(
                "telegram admin lookup failed: %s chat_id=%s", type(exc).__name__, message.chat.id
            )
            await self._say(message, "try_later", await self._locale(message))
            return False
        if status not in _ADMIN_STATUSES:
            await self._say(message, "not_admin", await self._locale(message))
            return False
        return True

    async def _link(self, message: Message, code: str, user_id: int) -> None:
        if not await self._admin_allowed(message, user_id):
            return
        async with self._state.engine.begin() as conn:
            repo = LinkRepository(conn)
            ok = await TelegramLinkService(repo).link_chat(message.chat.id, code)
            chat = await repo.linked_chat(message.chat.id)
        locale = chat.locale if chat else self._sender_locale(message)
        await self._say(message, "linked" if ok else "bad_code", locale)

    async def _notify(self, message: Message, arg: str, user_id: int, bot: BotIdentity) -> None:
        async with self._state.engine.begin() as conn:
            chat = await LinkRepository(conn).linked_chat(message.chat.id)
        if chat is None:
            await self._unlinked_hint(message, bot, self._sender_locale(message))
        elif arg not in ("on", "off"):
            await self._reply(message, notify_status(chat.locale, chat.notify), chat.locale)
        elif await self._admin_allowed(message, user_id):
            async with self._state.engine.begin() as conn:
                await LinkRepository(conn).set_notify([message.chat.id], arg == "on")
            await self._reply(message, notify_changed(chat.locale, arg == "on"), chat.locale)

    async def _chat(self, message: Message, text: str, bot: BotIdentity) -> None:
        async with self._state.engine.begin() as conn:
            chat = await LinkRepository(conn).linked_chat(message.chat.id)
        locale = chat.locale if chat else self._sender_locale(message)
        if not text:
            await self._say(message, "empty_question", locale)
            return
        limit = self._state.settings.agent_max_text_chars
        if len(text) > limit:
            await self._say(message, "too_long", locale, limit=limit)
            return
        if chat is None:
            await self._unlinked_hint(message, bot, locale)
            return
        # Agent errors leave the `with` first: the turn's transaction rolls back, then we answer.
        try:
            reply = await self._turn(text, chat.family_id)
        except (AgentBusyError, AgentBudgetExceededError, AgentUnavailableError) as exc:
            key = next(k for t, k in _AGENT_REPLIES if isinstance(exc, t))
            reply = localized(key, locale)
            logger.info("telegram turn refused: %s chat_id=%s", type(exc).__name__, message.chat.id)
        await self._reply(message, reply, locale)

    async def _turn(self, text: str, family_id: UUID) -> str:
        event = AgentEvent(family_id=str(family_id), channel="telegram", kind="message", text=text)
        async with self._state.engine.begin() as conn:
            return (await build_agent_gateway(self._state, conn).handle(event)).text

    @staticmethod
    def _sender_locale(message: Message) -> str:
        user = message.from_user
        return locale_from_language_code(user.language_code if user else None)

    async def _locale(self, message: Message) -> str:
        """The linked family's locale, else the sender's Telegram language."""
        async with self._state.engine.begin() as conn:
            chat = await LinkRepository(conn).linked_chat(message.chat.id)
        return chat.locale if chat else self._sender_locale(message)

    async def _unlinked_hint(self, message: Message, bot: BotIdentity, locale: str) -> None:
        command = "/link" if message.chat.type == "private" else f"/link@{bot.username}"
        await self._say(message, "unlinked", locale, command=command)

    async def _say(self, message: Message, key: str, locale: str, **values: object) -> None:
        await self._reply(message, localized(key, locale, **values), locale)

    async def _reply(self, message: Message, text: str, locale: str) -> None:
        for i, chunk in enumerate(
            self._chunks(text if text.strip() else localized("no_answer", locale))
        ):
            await self._sender.send(message.chat.id, chunk, message.message_id if i == 0 else None)

    @staticmethod
    def _chunks(text: str) -> list[str]:
        """Pieces of at most 4096 UTF-16 units (Telegram's unit), cut at a newline or space."""
        out = []
        while text:
            units = 0
            for i, ch in enumerate(text):
                units += 2 if ord(ch) > 0xFFFF else 1
                if units > MAX_MESSAGE_CHARS:
                    cut = i
                    break
            else:
                out.append(text)
                break
            boundary = max(text.rfind("\n", 0, cut), text.rfind(" ", 0, cut))
            cut = boundary + 1 if boundary > 0 else cut
            out.append(text[:cut])
            text = text[cut:]
        return out
