import logging
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)
from sqlalchemy.ext.asyncio import AsyncConnection

from app.channels.push.repository import PushRepository
from app.channels.push.rules import QuestWaiting
from app.channels.reminders import Reminder
from app.channels.telegram.sender import TelegramSender
from app.repositories.link_repository import LinkRepository

logger = logging.getLogger(__name__)


class TelegramChannel:
    """Plain-text reminders to the chats that opted in with `/notify on`."""

    name = "telegram"

    def __init__(self, sender: TelegramSender, site_url: str | None) -> None:
        self._sender = sender
        self._site_url = site_url.rstrip("/") if site_url else None

    async def targets(self, conn: AsyncConnection, family_id: UUID) -> list[int]:
        return await LinkRepository(conn).notify_chats(family_id)

    async def candidates(self, conn: AsyncConnection, older_than: datetime) -> list[QuestWaiting]:
        return await PushRepository(conn).quest_waiting_candidates(older_than, self.name)

    async def deliver(self, targets: Sequence[int], reminder: Reminder) -> tuple[int, list[int]]:
        text = reminder.text
        if self._site_url:
            text += f"\n{self._site_url}/{reminder.locale}/adventure"
        delivered, gone = 0, []
        for chat_id in targets:
            try:
                await self._sender.send(chat_id, text)
                delivered += 1
            except (TelegramForbiddenError, TelegramMigrateToChat):
                gone.append(chat_id)  # bot blocked or removed, or the group got a new id
            except TelegramBadRequest as exc:
                if "chat not found" in exc.message.lower():
                    gone.append(chat_id)
                else:
                    logger.warning("telegram reminder failed: %s", type(exc).__name__)
            except TelegramAPIError as exc:
                logger.warning("telegram reminder failed: %s", type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 (sender boundary: one chat must not stop the rest)
                logger.warning("telegram reminder failed: %s", type(exc).__name__)
        return delivered, gone

    async def forget(self, conn: AsyncConnection, gone: list[int]) -> None:
        await LinkRepository(conn).set_notify(gone, False)
