import asyncio

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.channels.telegram import texts
from tests.telegram.conftest import BOT, HEADER, SECRET, post_update, update
from tests.telegram.test_notify import linked
from tests.telegram.test_webhook import issue_code
from tests.test_agent_api import make_member


def from_user(language_code: str | None) -> dict:
    user = {"id": 5, "is_bot": False, "first_name": "Pa"}
    return {"from": user | ({"language_code": language_code} if language_code else {})}


@pytest.mark.parametrize(
    ("code", "locale"),
    [
        ("ru", "ru"),
        ("RU", "ru"),
        ("es", "es"),
        ("es-419", "es"),
        ("zh-hans", "zh-CN"),
        ("zh", "zh-CN"),
        ("zh_TW", "zh-CN"),
        ("pt-BR", "en"),
        ("en", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_telegram_language_code_maps_to_a_locale(code, locale) -> None:
    assert texts.locale_from_language_code(code) == locale


def test_every_table_has_all_four_locales() -> None:
    assert texts.TABLES
    for table in texts.TABLES:
        assert set(table) == set(texts.LOCALES)


def test_unknown_locale_falls_back_to_english() -> None:
    assert texts.localized("busy", "pt") == texts.localized("busy", "en")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "es-419",
            "Primero conecta este chat: copia el código del sitio"
            f" y envía /link@{BOT.username} <código>.",
        ),
        (
            "ru",
            "Сначала подключите этот чат: возьмите код на сайте"
            f" и отправьте /link@{BOT.username} <код>.",
        ),
        ("zh-hans", "请先连接此聊天"),
        (None, f"link this chat first: /link@{BOT.username} <code> from the site"),
        ("pt-BR", f"link this chat first: /link@{BOT.username} <code> from the site"),
    ],
)
async def test_unlinked_sender_gets_the_hint_in_their_telegram_language(
    tg, sender, code, expected
) -> None:
    await post_update(tg, update(1, "/ask hi", **from_user(code)))
    assert expected in sender.sent[-1].text


async def test_unlinked_private_hint_in_spanish_uses_plain_link(tg, sender) -> None:
    await post_update(tg, update(1, "hi", 42, **from_user("es")))
    assert (
        sender.sent[-1].text
        == "Primero conecta este chat: copia el código del sitio y envía /link <código>."
    )


async def test_unlinked_non_admin_refusal_follows_sender_language(tg, sender) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    sender.admins.clear()
    await post_update(tg, update(1, f"/link {code}", **from_user("es-419")))
    assert sender.sent[-1].text == "Solo los administradores del chat pueden conectarlo."


async def test_unlinked_bad_code_follows_sender_language(tg, sender) -> None:
    await post_update(tg, update(1, "/link nope", **from_user("zh-hans")))
    assert sender.sent[-1].text == "验证码无效或已过期。"


async def test_link_success_is_in_the_family_locale_not_the_sender_language(
    tg, sender, db_fetch
) -> None:
    cookie, family_id = await make_member(tg)
    await db_fetch("UPDATE families SET locale = 'es' WHERE id = $1::uuid RETURNING 1", family_id)
    code = await issue_code(tg, family_id, cookie)
    await post_update(tg, update(1, f"/link {code}", **from_user("ru")))
    assert sender.sent[-1].text == "Chat conectado."


async def test_linked_chat_empty_question_follows_family_locale(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch, locale="es")
    await post_update(tg, update(2, "/ask", **from_user("ru")))
    assert sender.sent[-1].text == "Escribe una pregunta después de /ask."


async def test_linked_ru_chat_too_long_reply_is_russian(tg, sender, db_fetch) -> None:
    await linked(tg, db_fetch, locale="ru")
    await post_update(tg, update(2, f"@{BOT.username} " + "x" * 2001, **from_user("en")))
    assert sender.sent[-1].text == "Сообщение слишком длинное (не больше 2000 символов)."


async def test_linked_ru_chat_limit_reply_is_russian(tg, sender, agent, db_fetch) -> None:
    await linked(tg, db_fetch, locale="ru")

    def over(messages, info):
        raise UsageLimitExceeded("limit")

    with agent.override(model=FunctionModel(over)):
        await post_update(tg, update(2, f"@{BOT.username} hi"))
    assert sender.sent[-1].text == "На сегодня лимит исчерпан."


async def test_linked_ru_chat_busy_reply_is_russian(tg, sender, agent, db_fetch) -> None:
    await linked(tg, db_fetch, locale="ru")

    async def slow(messages, info):
        await asyncio.sleep(0.4)
        return ModelResponse(parts=[TextPart("done")])

    with agent.override(model=FunctionModel(slow)):
        for n, delay in ((2, 0.15), (3, 0)):
            await tg.post(
                "/api/v1/telegram/webhook",
                json=update(n, f"@{BOT.username} q"),
                headers={HEADER: SECRET},
            )
            await asyncio.sleep(delay)
        await post_update(tg, update(4, "/notify"))
    assert "Подождите, я ещё отвечаю." in [s.text for s in sender.sent]
