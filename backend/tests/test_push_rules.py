from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.channels.push.rules import QuestWaiting, quest_waiting_due
from app.channels.push.texts import chapter_ready_text, quest_waiting_text

MOSCOW = ZoneInfo("Europe/Moscow")  # UTC+3
HOURS = range(17, 20)
NOW = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)  # 18:00 in Moscow
WAITING = QuestWaiting(uuid4(), "ru", "Q", NOW - timedelta(hours=29), None, None, 0)


def due(c: QuestWaiting = WAITING, now: datetime = NOW, tz: ZoneInfo = MOSCOW) -> bool:
    return quest_waiting_due(c, now, tz, HOURS)


def test_due_in_the_evening_window_after_20_hours() -> None:
    assert due()


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(13, 59, False), (14, 0, True), (16, 59, True), (17, 0, False)],  # 16:59 UTC = 19:59 Moscow
)
def test_window_is_17_00_to_19_59_local(hour: int, minute: int, expected: bool) -> None:
    now = NOW.replace(hour=hour, minute=minute)
    assert due(now=now) is expected


def test_window_follows_the_subscription_time_zone() -> None:
    assert not due(tz=ZoneInfo("Asia/Tokyo"))  # 00:00 there
    assert due(now=NOW.replace(hour=8), tz=ZoneInfo("Asia/Tokyo"))  # 17:00 there


def test_quest_must_wait_20_hours() -> None:
    young = replace(WAITING, quest_at=NOW - timedelta(hours=19, minutes=59))
    assert not due(young)
    assert due(replace(WAITING, quest_at=NOW - timedelta(hours=20)))


def test_not_when_the_family_was_in_the_game_today_local() -> None:
    assert not due(replace(WAITING, last_active_at=NOW - timedelta(hours=5)))  # 13:00 Moscow
    # 20:30 UTC yesterday = 23:30 Moscow yesterday: another local day
    assert due(replace(WAITING, last_active_at=NOW - timedelta(hours=18, minutes=30)))


def test_one_per_local_day() -> None:
    assert not due(replace(WAITING, last_sent_at=NOW - timedelta(hours=1), unanswered=1))
    assert due(replace(WAITING, last_sent_at=NOW - timedelta(hours=24), unanswered=1))


def test_three_unanswered_silence_until_the_family_returns() -> None:
    sent = NOW - timedelta(days=2)
    silent = replace(WAITING, last_sent_at=sent, unanswered=3)
    assert not due(silent)
    returned = replace(silent, last_active_at=sent + timedelta(hours=3))  # yesterday-ish
    assert returned.effective_unanswered == 0 and due(returned)
    assert replace(silent, unanswered=2).effective_unanswered == 2


@pytest.mark.parametrize("locale", ["ru", "en", "es", "zh-CN"])
def test_texts_exist_in_every_locale_and_carry_only_titles(locale: str) -> None:
    waiting = quest_waiting_text(locale, "World", "Quest")
    assert "World" in waiting and "Quest" in waiting
    assert "World" in chapter_ready_text(locale, "World")
    assert "Quest" in quest_waiting_text(locale, None, "Quest")
    assert chapter_ready_text(locale, None)
