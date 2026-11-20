import json
import logging
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from app.channels.push.repository import PushRepository
from app.channels.push.rules import QuestWaiting
from app.channels.push.sender import PushFailed, PushSender, PushSubscription, SubscriptionGone
from app.channels.reminders import Reminder

logger = logging.getLogger(__name__)
TTL_S = {"chapter_ready": 3600, "quest_waiting": 3 * 3600}


class PushChannel:
    name = "push"

    def __init__(self, sender: PushSender) -> None:
        self._sender = sender

    async def targets(self, conn: AsyncConnection, family_id: UUID) -> list[PushSubscription]:
        return await PushRepository(conn).family_subscriptions(family_id)

    async def candidates(self, conn: AsyncConnection, older_than: datetime) -> list[QuestWaiting]:
        return await PushRepository(conn).quest_waiting_candidates(older_than, self.name)

    async def deliver(
        self, targets: Sequence[PushSubscription], reminder: Reminder
    ) -> tuple[int, list[UUID]]:
        payload = self._payload(reminder)
        delivered, gone = 0, []
        for sub in targets:
            try:
                await self._sender.send(sub, payload, TTL_S[reminder.kind])
                delivered += 1
            except SubscriptionGone:
                gone.append(sub.id)
            except PushFailed as exc:
                logger.warning("push send failed: %s", exc)
            except Exception as exc:  # noqa: BLE001 (sender boundary: one device must not stop the rest)
                logger.warning("push send failed: %s", type(exc).__name__)
        return delivered, gone

    async def forget(self, conn: AsyncConnection, gone: list[UUID]) -> None:
        await PushRepository(conn).delete_ids(gone)

    @staticmethod
    def _payload(reminder: Reminder) -> str:
        data = {
            "title": "Nuvistela",
            "body": reminder.text,
            "url": f"/{reminder.locale}/adventure",
            "kind": reminder.kind,
        }
        return json.dumps(data, ensure_ascii=False)
