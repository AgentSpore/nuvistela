import pytest

from tests.telegram.conftest import BOT, post_update, update
from tests.telegram.test_webhook import CHAT, issue_code, link
from tests.test_agent_api import make_member

PRIVATE = 42


async def notify_flag(db_fetch, chat_id: int = CHAT) -> bool:
    return (await db_fetch("SELECT notify FROM tg_chats WHERE chat_id = $1", chat_id))[0]["notify"]


async def linked(tg, db_fetch, chat_id: int = CHAT, locale: str | None = None) -> str:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1, chat_id)
    if locale:
        await db_fetch(
            "UPDATE families SET locale = $2 WHERE id = $1::uuid RETURNING 1", family_id, locale
        )
    return family_id


async def test_notify_is_off_until_an_admin_turns_it_on_and_off(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch)
    assert await notify_flag(db_fetch) is False
    await post_update(tg, update(2, "/notify on"))
    assert await notify_flag(db_fetch) is True
    assert "Напоминания включены" in sender.sent[-1].text
    await post_update(tg, update(3, f"/notify@{BOT.username} off"))
    assert await notify_flag(db_fetch) is False
    assert sender.sent[-1].text == "Напоминания выключены."


async def test_notify_in_a_group_needs_an_admin(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch)
    sender.admins.clear()
    await post_update(tg, update(2, "/notify on"))
    assert await notify_flag(db_fetch) is False
    assert sender.sent[-1].text == "Подключить чат могут только его администраторы."


async def test_notify_admin_lookup_error_asks_to_retry(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch)
    sender.status_fails = True
    await post_update(tg, update(2, "/notify on"))
    assert await notify_flag(db_fetch) is False
    assert sender.sent[-1].text == "Не получилось. Попробуйте чуть позже."


async def test_notify_in_a_private_chat_needs_no_admin(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch, PRIVATE)
    sender.admins.clear()
    await post_update(tg, update(2, "/notify on", PRIVATE))
    assert await notify_flag(db_fetch, PRIVATE) is True


async def test_notify_in_an_unlinked_chat_points_to_link(tg, sender) -> None:
    await post_update(tg, update(1, "/notify on"))
    assert (
        sender.sent[-1].text == f"link this chat first: /link@{BOT.username} <code> from the site"
    )


@pytest.mark.parametrize("text", ["/notify", "/notify maybe"])
async def test_notify_without_a_valid_argument_shows_status_and_changes_nothing(
    tg, sender, db_fetch, text
) -> None:
    await linked(tg, db_fetch)
    await post_update(tg, update(2, text))
    assert (
        sender.sent[-1].text
        == "Напоминания выключены. Включить: /notify on, выключить: /notify off."
    )
    assert await notify_flag(db_fetch) is False


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Reminders are on:"),
        ("es", "Recordatorios activados:"),
        ("zh-CN", "提醒已开启"),
    ],
)
async def test_notify_reply_follows_the_family_locale(
    tg, sender, db_fetch, locale, expected
) -> None:
    await linked(tg, db_fetch, locale=locale)
    await post_update(tg, update(2, "/notify on"))
    assert sender.sent[-1].text.startswith(expected)
