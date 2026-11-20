import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)
from aiogram.methods import SendMessage
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import text

from app.channels.push.channel import PushChannel
from app.channels.push.sender import PushFailed, PushSubscription, SubscriptionGone
from app.channels.telegram.reminders import TelegramChannel
from app.channels.telegram.sender import BotIdentity
from app.core.config import Settings
from app.main import create_app
from app.repositories.job_repository import JobRepository
from app.repositories.link_repository import LinkRepository
from app.workers.reminder_worker import ReminderWorker
from tests.conftest import _client
from tests.test_world_api import adult_with_child

NOW = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)  # 18:00 in Moscow
OLD_QUEST = NOW - timedelta(hours=29)


@dataclass
class FakeSender:
    sent: list[tuple[str, dict, int]] = field(default_factory=list)
    gone: set[str] = field(default_factory=set)
    broken: set[str] = field(default_factory=set)

    async def send(self, sub: PushSubscription, payload: str, ttl: int) -> None:
        if sub.endpoint in self.gone:
            raise SubscriptionGone
        if sub.endpoint in self.broken:
            raise PushFailed("push service answered 500")
        self.sent.append((sub.endpoint, json.loads(payload), ttl))

    def to(self, endpoint: str) -> list[dict]:
        return [payload for ep, payload, _ in self.sent if ep == endpoint]


@dataclass
class FakeTelegram:
    sent: list[tuple[int, str]] = field(default_factory=list)
    forbidden: set[int] = field(default_factory=set)
    missing: set[int] = field(default_factory=set)
    migrated: set[int] = field(default_factory=set)

    async def me(self) -> BotIdentity:
        return BotIdentity(id=1, username="bot")

    async def chat_member_status(self, chat_id: int, user_id: int) -> str:
        return "member"

    async def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        if chat_id in self.forbidden:
            raise TelegramForbiddenError(SendMessage(chat_id=chat_id, text=""), "bot was blocked")
        if chat_id in self.migrated:
            raise TelegramMigrateToChat(SendMessage(chat_id=chat_id, text=""), "migrated", 1)
        if chat_id in self.missing:
            raise TelegramBadRequest(SendMessage(chat_id=chat_id, text=""), "chat not found")
        self.sent.append((chat_id, text))

    def to(self, chat_id: int) -> list[str]:
        return [text for cid, text in self.sent if cid == chat_id]


@dataclass
class Family:
    id: UUID
    endpoint: str


@dataclass
class Env:
    client: AsyncClient
    sender: FakeSender
    telegram: FakeTelegram
    worker: ReminderWorker
    clock: list[datetime]


@pytest.fixture
async def env(postgres_url: str, agent) -> AsyncIterator[Env]:
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        cookie_secure=False,
        vapid_public_key="pub",
        vapid_private_key=SecretStr("priv"),
        vapid_subject="mailto:ops@example.test",
        telegram_bot_token=SecretStr("1:tok"),
        telegram_webhook_secret=SecretStr("hook-secret"),
        site_url="https://nuvistela.test/",
    )
    sender, telegram, clock = FakeSender(), FakeTelegram(), [NOW]
    app = create_app(settings, agent=agent, push_sender=sender, telegram_sender=telegram)
    async for c in _client(app):
        app.state.reminder_worker.cancel()  # tests drive the worker by hand
        channels = [PushChannel(sender), TelegramChannel(telegram, settings.site_url)]
        worker = ReminderWorker(app.state.engine, channels, settings, lambda: clock[0])
        yield Env(c, sender, telegram, worker, clock)
        async with (
            app.state.engine.begin() as conn
        ):  # a deferred job must not fall due in a later test
            await conn.execute(text("DELETE FROM jobs WHERE kind = 'notify'"))


async def subscribed_family(env: Env, tz: str = "Europe/Moscow") -> Family:
    adult, _, fid, *_ = await adult_with_child(env.client)
    endpoint = f"https://fcm.googleapis.com/fcm/send/{uuid4()}"
    body = {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}, "tz": tz}
    assert (
        await env.client.post("/api/v1/push/subscriptions", headers=adult, json=body)
    ).is_success
    return Family(UUID(fid), endpoint)


@pytest.fixture
def open_quest(db_fetch):
    async def run(family: Family, created_at: datetime = OLD_QUEST) -> None:
        await db_fetch(
            "INSERT INTO quests (family_id, seq, title, description, skill, source, created_at)"
            " VALUES ($1, 1, 'Одно слово', 'd', 'care', 'template', $2)",
            family.id,
            created_at,
        )

    return run


@pytest.fixture
def sent_events(db_fetch):
    async def run(family: Family) -> list[str]:
        rows = await db_fetch(
            "SELECT props FROM events WHERE kind = 'reminder_sent' AND family_id = $1", family.id
        )
        return [r["props"] for r in rows]

    return run


async def queue_ready(env: Env, family: Family, age: timedelta = timedelta(0)) -> None:
    """Queue a "chapter ready" job `age` old; the clock follows the real one (the DB polls do)."""
    env.clock[0] = datetime.now(UTC)
    async with env.worker._engine.begin() as conn:
        at = (env.clock[0] - age).isoformat()
        await JobRepository(conn).enqueue("notify", family.id, {"ready_at": at})


async def test_chapter_ready_goes_to_the_device_without_names(env: Env, sent_events) -> None:
    family = await subscribed_family(env)
    await queue_ready(env, family)
    assert await env.worker.run_notify_once()
    (payload,) = env.sender.to(family.endpoint)
    assert payload == {
        "title": "Nuvistela",
        "body": "Глава готова",
        "url": "/ru/adventure",
        "kind": "chapter_ready",
    }
    assert await sent_events(family) == ['{"kind": "chapter_ready", "channel": "push"}']


async def test_no_chapter_push_while_the_tab_polls(env: Env, db_fetch, sent_events) -> None:
    family = await subscribed_family(env)
    await db_fetch("UPDATE families SET last_adventure_poll_at = now() WHERE id = $1", family.id)
    await queue_ready(env, family)
    assert await env.worker.run_notify_once()
    assert env.sender.to(family.endpoint) == [] and await sent_events(family) == []
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = now() - interval '60 seconds' WHERE id = $1",
        family.id,
    )
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert len(env.sender.to(family.endpoint)) == 1


async def test_a_quick_leaver_still_gets_the_chapter_after_the_window(env: Env, db_fetch) -> None:
    family = await subscribed_family(env)
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = now() - interval '10 seconds' WHERE id = $1",
        family.id,
    )
    await queue_ready(env, family)
    assert await env.worker.run_notify_once()
    assert env.sender.to(family.endpoint) == []
    (job,) = await db_fetch(
        "SELECT status, last_error, extract(epoch FROM next_run_at - now()) AS wait"
        " FROM jobs WHERE family_id = $1",
        family.id,
    )
    assert job["status"] == "pending" and job["last_error"] is None
    assert 4 < job["wait"] < 8  # last poll + 15 s window + margin
    assert not await env.worker.run_notify_once()  # not due yet
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = now() - interval '20 seconds' WHERE id = $1",
        family.id,
    )  # the window has passed without a new poll
    await db_fetch("UPDATE jobs SET next_run_at = now() WHERE family_id = $1", family.id)
    assert await env.worker.run_notify_once()
    assert len(env.sender.to(family.endpoint)) == 1
    rows = await db_fetch("SELECT status FROM jobs WHERE family_id = $1", family.id)
    assert [r["status"] for r in rows] == ["done"]


async def test_a_player_who_keeps_watching_ends_in_a_quiet_drop(env: Env, db_fetch) -> None:
    family = await subscribed_family(env)
    await db_fetch("UPDATE families SET last_adventure_poll_at = now() WHERE id = $1", family.id)
    await queue_ready(env, family)
    for _ in range(4):  # still polling on every re-run: deferred again, never failed
        assert await env.worker.run_notify_once()
        await db_fetch("UPDATE jobs SET next_run_at = now() WHERE family_id = $1", family.id)
        await db_fetch(
            "UPDATE families SET last_adventure_poll_at = now() WHERE id = $1", family.id
        )
    (job,) = await db_fetch("SELECT status, last_error FROM jobs WHERE family_id = $1", family.id)
    assert job["status"] == "pending" and job["last_error"] is None
    await db_fetch(
        "UPDATE jobs SET payload = jsonb_build_object('ready_at', $2::text) WHERE family_id = $1",
        family.id,
        (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
    )
    assert await env.worker.run_notify_once()
    (job,) = await db_fetch("SELECT status, last_error FROM jobs WHERE family_id = $1", family.id)
    assert job["status"] == "done" and job["last_error"] is None
    assert env.sender.to(family.endpoint) == []


async def test_stale_chapter_job_is_dropped_and_completed(env: Env, db_fetch) -> None:
    family = await subscribed_family(env)
    await queue_ready(env, family, timedelta(minutes=10))
    await env.worker.run_notify_once()
    assert env.sender.to(family.endpoint) == []
    rows = await db_fetch("SELECT status FROM jobs WHERE family_id = $1", family.id)
    assert [r["status"] for r in rows] == ["done"]


async def test_gone_subscription_is_deleted_and_other_errors_keep_it(
    env: Env, db_fetch, sent_events
) -> None:
    family = await subscribed_family(env)
    env.sender.broken.add(family.endpoint)
    await queue_ready(env, family)
    await env.worker.run_notify_once()  # a failing device must not raise
    assert await sent_events(family) == []
    assert (
        len(await db_fetch("SELECT 1 FROM push_subscriptions WHERE family_id = $1", family.id)) == 1
    )
    env.sender.broken.clear()
    env.sender.gone.add(family.endpoint)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert await db_fetch("SELECT 1 FROM push_subscriptions WHERE family_id = $1", family.id) == []
    assert await sent_events(family) == []


async def test_quest_waiting_is_sent_once_a_day_with_titles_only(
    env: Env, open_quest, sent_events, db_fetch
) -> None:
    family = await subscribed_family(env)
    await open_quest(family)
    await env.worker.run_reminders_once()
    await env.worker.run_reminders_once()
    (payload,) = env.sender.to(family.endpoint)
    assert payload["body"] == "Новое задание — «Одно слово»" and payload["kind"] == "quest_waiting"
    assert payload["url"] == "/ru/adventure"
    assert await sent_events(family) == ['{"kind": "quest_waiting", "channel": "push"}']
    state = await db_fetch("SELECT unanswered FROM reminder_state WHERE family_id = $1", family.id)
    assert state[0]["unanswered"] == 1
    env.clock[0] = NOW + timedelta(days=1)  # next local evening
    await env.worker.run_reminders_once()
    assert len(env.sender.to(family.endpoint)) == 2


@pytest.mark.parametrize(
    ("clock", "tz", "quest_age_h"),
    [
        (NOW.replace(hour=9), "Europe/Moscow", 29),  # 12:00 local
        (NOW, "Asia/Tokyo", 29),  # 00:00 local
        (NOW, "Europe/Moscow", 5),  # quest too young
    ],
)
async def test_quest_waiting_holds_back_outside_its_conditions(
    env: Env, open_quest, clock: datetime, tz: str, quest_age_h: int
) -> None:
    family = await subscribed_family(env, tz)
    await open_quest(family, clock - timedelta(hours=quest_age_h))
    env.clock[0] = clock
    await env.worker.run_reminders_once()
    assert env.sender.to(family.endpoint) == []


async def test_quest_waiting_skips_a_family_that_played_today(
    env: Env, open_quest, db_fetch
) -> None:
    family = await subscribed_family(env)
    await open_quest(family)
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = $2 WHERE id = $1",
        family.id,
        NOW - timedelta(hours=4),  # 14:00 Moscow, same local day
    )
    await env.worker.run_reminders_once()
    assert env.sender.to(family.endpoint) == []


async def test_three_unanswered_reminders_then_silence_until_a_visit(
    env: Env, open_quest, db_fetch
) -> None:
    family = await subscribed_family(env)
    await open_quest(family)
    for day in range(5):
        env.clock[0] = NOW + timedelta(days=day)
        await env.worker.run_reminders_once()
    assert len(env.sender.to(family.endpoint)) == 3
    env.clock[0] = NOW + timedelta(days=5)  # the family visited yesterday evening, then left
    await db_fetch(
        "UPDATE families SET last_adventure_poll_at = $2 WHERE id = $1",
        family.id,
        NOW + timedelta(days=4, hours=-2),
    )
    await env.worker.run_reminders_once()
    assert len(env.sender.to(family.endpoint)) == 4


async def test_two_processes_remind_a_family_once(env: Env, open_quest) -> None:
    family = await subscribed_family(env)
    await open_quest(family)
    await asyncio.gather(env.worker.run_reminders_once(), env.worker.run_reminders_once())
    assert len(env.sender.to(family.endpoint)) == 1


async def test_a_day_nothing_was_delivered_does_not_count_toward_silence(
    env: Env, open_quest
) -> None:
    family = await subscribed_family(env)
    await open_quest(family)
    env.sender.broken.add(family.endpoint)
    for day in range(3):  # push service down for three evenings
        env.clock[0] = NOW + timedelta(days=day)
        await env.worker.run_reminders_once()
    env.sender.broken.clear()
    env.clock[0] = NOW + timedelta(days=3)
    await env.worker.run_reminders_once()
    assert len(env.sender.to(family.endpoint)) == 1


@pytest.fixture
def join_chat(db_fetch):
    async def run(family: Family, notify: bool = True) -> int:
        chat_id = -uuid4().int % 10**12
        await db_fetch(
            "INSERT INTO tg_chats (chat_id, family_id, notify) VALUES ($1, $2, $3) RETURNING 1",
            chat_id,
            family.id,
            notify,
        )
        return chat_id

    return run


async def test_chapter_ready_goes_to_telegram_with_a_link_and_its_own_event(
    env: Env, join_chat, sent_events
) -> None:
    family = await subscribed_family(env)
    chat = await join_chat(family)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert env.telegram.to(chat) == ["Глава готова\nhttps://nuvistela.test/ru/adventure"]
    assert len(env.sender.to(family.endpoint)) == 1  # the device is reminded too
    assert sorted(await sent_events(family)) == [
        '{"kind": "chapter_ready", "channel": "push"}',
        '{"kind": "chapter_ready", "channel": "telegram"}',
    ]


async def test_a_migrated_group_withdraws_consent(env: Env, join_chat, db_fetch) -> None:
    family = await subscribed_family(env)
    chat = await join_chat(family)
    env.telegram.migrated.add(chat)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    rows = await db_fetch("SELECT notify FROM tg_chats WHERE chat_id = $1", chat)
    assert rows[0]["notify"] is False


@pytest.mark.parametrize(("push_on", "expected"), [(False, False), (True, True)])
async def test_chapter_worker_queues_notify_jobs_only_with_a_reminder_worker(
    postgres_url: str, agent, monkeypatch, push_on: bool, expected: bool
) -> None:
    started: list[bool] = []

    class RecordingChapterWorker:
        def __init__(self, engine, writer, settings, notify: bool = False) -> None:
            started.append(notify)

        async def run_forever(self) -> None:
            await asyncio.Event().wait()

    monkeypatch.setattr("app.main.ChapterWorker", RecordingChapterWorker)
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        openrouter_api_key=SecretStr("k"),
        telegram_bot_token=SecretStr("1:tok"),
        telegram_webhook_secret=SecretStr("bad secret!"),  # Telegram stays off
        vapid_public_key="pub" if push_on else None,
        vapid_private_key=SecretStr("priv") if push_on else None,
        vapid_subject="mailto:ops@example.test" if push_on else None,
    )
    app = create_app(settings, agent=agent, push_sender=FakeSender())
    async for _ in _client(app):
        assert app.state.telegram is None
    assert started == [expected]


async def test_chat_without_consent_gets_nothing(env: Env, join_chat) -> None:
    family = await subscribed_family(env)
    chat = await join_chat(family, notify=False)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert env.telegram.to(chat) == []


async def test_telegram_alone_is_enough_and_a_tab_open_blocks_it(
    env: Env, join_chat, db_fetch
) -> None:
    family = await subscribed_family(env)
    await db_fetch("DELETE FROM push_subscriptions WHERE family_id = $1", family.id)
    chat = await join_chat(family)
    await db_fetch("UPDATE families SET last_adventure_poll_at = now() WHERE id = $1", family.id)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert env.telegram.to(chat) == []
    await db_fetch("UPDATE families SET last_adventure_poll_at = NULL WHERE id = $1", family.id)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    assert len(env.telegram.to(chat)) == 1


async def test_quest_waiting_over_telegram_uses_the_push_time_zone(
    env: Env, join_chat, open_quest, db_fetch
) -> None:
    family = await subscribed_family(env)
    chat = await join_chat(family)
    await open_quest(family)
    await env.worker.run_reminders_once()
    assert env.telegram.to(chat) == [
        "Новое задание — «Одно слово»\nhttps://nuvistela.test/ru/adventure"
    ]
    rows = await db_fetch(
        "SELECT channel, unanswered FROM reminder_state WHERE family_id = $1 ORDER BY channel",
        family.id,
    )
    assert [(r["channel"], r["unanswered"]) for r in rows] == [("push", 1), ("telegram", 1)]


async def test_quest_waiting_skips_telegram_without_a_push_time_zone(
    env: Env, join_chat, open_quest, db_fetch
) -> None:
    family = await subscribed_family(env)
    chat = await join_chat(family)
    await open_quest(family)
    await db_fetch("DELETE FROM push_subscriptions WHERE family_id = $1", family.id)
    await env.worker.run_reminders_once()
    assert env.telegram.to(chat) == []


async def test_blocked_bot_or_missing_chat_withdraws_consent(env: Env, join_chat, db_fetch) -> None:
    family = await subscribed_family(env)
    blocked, missing, fine = (
        await join_chat(family),
        await join_chat(family),
        await join_chat(family),
    )
    env.telegram.forbidden.add(blocked)
    env.telegram.missing.add(missing)
    await queue_ready(env, family)
    await env.worker.run_notify_once()
    rows = await db_fetch("SELECT chat_id, notify FROM tg_chats WHERE family_id = $1", family.id)
    assert {r["chat_id"]: r["notify"] for r in rows} == {blocked: False, missing: False, fine: True}
    assert len(env.telegram.to(fine)) == 1


async def test_chat_notify_is_off_by_default_and_rebinding_to_another_family_resets_it(
    env: Env, join_chat, db_fetch
) -> None:
    family, other = await subscribed_family(env), await subscribed_family(env)
    chat = await join_chat(family)
    bare = chat - 1
    async with env.worker._engine.begin() as conn:
        await LinkRepository(conn).bind_chat(bare, family.id)
        await LinkRepository(conn).bind_chat(chat, family.id)  # same family: consent stays
    flags = {
        r["chat_id"]: r["notify"]
        for r in await db_fetch(
            "SELECT chat_id, notify FROM tg_chats WHERE chat_id = ANY($1)", [bare, chat]
        )
    }
    assert flags == {bare: False, chat: True}
    async with env.worker._engine.begin() as conn:
        await LinkRepository(conn).bind_chat(chat, other.id)
    rows = await db_fetch("SELECT notify FROM tg_chats WHERE chat_id = $1", chat)
    assert rows[0]["notify"] is False
