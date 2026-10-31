"""The only door to Telegram: tests replace `TelegramSender`, so the network is never touched."""

from dataclasses import dataclass
from typing import Protocol

from aiogram import Bot
from aiogram.types import ReplyParameters


@dataclass(frozen=True, slots=True)
class BotIdentity:
    id: int
    username: str


class TelegramSender(Protocol):
    async def me(self) -> BotIdentity: ...

    async def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None: ...

    async def chat_member_status(self, chat_id: int, user_id: int) -> str: ...


class AiogramSender:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def me(self) -> BotIdentity:
        me = await self._bot.me()  # aiogram caches the getMe result per Bot
        return BotIdentity(id=me.id, username=me.username or "")

    async def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        reply = (
            ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)
            if reply_to is not None
            else None
        )
        await self._bot.send_message(chat_id, text, reply_parameters=reply)

    async def chat_member_status(self, chat_id: int, user_id: int) -> str:
        return (await self._bot.get_chat_member(chat_id, user_id)).status

    async def close(self) -> None:
        await self._bot.session.close()
