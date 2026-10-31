"""Runs updates after the webhook has answered 200: Telegram retries slow responses."""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from aiogram.types import Update

logger = logging.getLogger(__name__)


class UpdateRunner:
    """Tracked background tasks plus an in-memory `update_id` dedupe.

    Skeleton limits: the dedupe window is per process and lost on restart, so a redelivery after
    a restart can run twice. A persistent dedupe (table keyed by update_id) is a later stage.
    """

    def __init__(
        self,
        process: Callable[[Update], Awaitable[None]],
        max_seen: int = 1000,
        max_concurrent: int = 8,
    ) -> None:
        self._process = process
        self._max_seen = max_seen
        self._slots = asyncio.Semaphore(max_concurrent)
        self._seen: OrderedDict[int, None] = OrderedDict()
        self._tasks: set[asyncio.Task[None]] = set()  # strong refs: the loop keeps only weak ones

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def submit(self, update: Update) -> bool:
        """Start processing; False when this `update_id` was already seen."""
        if update.update_id in self._seen:
            return False
        self._seen[update.update_id] = None
        if len(self._seen) > self._max_seen:
            self._seen.popitem(last=False)
        task = asyncio.create_task(self._run(update))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _run(self, update: Update) -> None:
        try:
            async with self._slots:
                await self._process(update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 (task boundary: nobody awaits it, log class only)
            chat = update.message.chat.id if update.message else None
            logger.error("telegram update failed: %s chat_id=%s", type(exc).__name__, chat)

    async def drain(self) -> None:
        """Wait for running tasks (tests and shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self, grace_s: float = 10.0) -> None:
        """Let tasks finish for `grace_s`, then cancel what is left and wait for it."""
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=grace_s)
        for task in list(self._tasks):
            task.cancel()
        await self.drain()
