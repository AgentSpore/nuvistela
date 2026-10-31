import asyncio
from pathlib import Path

from aiogram.types import Update
from pydantic import SecretStr, ValidationError
from pydantic_ai.models.function import FunctionModel
from pytest import raises

from app.channels.telegram.runner import UpdateRunner
from app.core.config import Settings
from app.main import create_app
from tests.conftest import _client
from tests.telegram.conftest import BOT, post_update, update
from tests.telegram.test_webhook import issue_code, link
from tests.test_agent_api import Recorder, make_member


async def linked(tg, sender) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()


async def test_plain_text_mention_without_entity_is_ignored(tg, sender, agent) -> None:
    await linked(tg, sender)
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, f"@{BOT.username} hi", entities=[]))
    assert sender.sent == [] and rec.seen == []


async def test_mention_entity_matches_exactly_not_by_prefix(tg, sender, agent) -> None:
    await linked(tg, sender)
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, f"@{BOT.username}x hi"))
    assert sender.sent == [] and rec.seen == []


async def test_mention_entity_is_case_insensitive(tg, sender, agent) -> None:
    await linked(tg, sender)
    with agent.override(model=FunctionModel(Recorder("ok"))):
        await post_update(tg, update(2, f"@{BOT.username.upper()} hi"))
    assert [s.text for s in sender.sent] == ["ok"]


async def test_ask_command_goes_to_agent_with_its_text(tg, sender, agent) -> None:
    await linked(tg, sender)
    rec = Recorder("ok")
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, "/ask what now?"))
        await post_update(tg, update(3, f"/ask@{BOT.username} and then?"))
    assert rec.prompts() == ["what now?", "and then?"]  # history, then the new turn
    assert [s.text for s in sender.sent] == ["ok", "ok"]


async def test_command_for_another_bot_is_ignored(tg, sender, agent) -> None:
    await linked(tg, sender)
    cookie, family_id = await make_member(tg, "B")
    code = await issue_code(tg, family_id, cookie)
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, "/ask@otherbot hi"))
        await post_update(tg, update(3, f"/link@otherbot {code}"))
    assert sender.sent == [] and rec.seen == []


async def test_unlinked_group_hint_names_the_bot_in_link_command(tg, sender) -> None:
    await post_update(tg, update(1, "/ask hi"))
    assert sender.sent[0].text == f"link this chat first: /link@{BOT.username} <code> from the site"


async def test_unlinked_private_hint_is_plain_link(tg, sender) -> None:
    await post_update(tg, update(1, "hi", chat_id=42))
    assert sender.sent[0].text == "link this chat first: /link <code> from the site"


async def test_empty_question_gets_hint_and_runs_no_turn(tg, sender, agent) -> None:
    await linked(tg, sender)
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, "/ask"))
        await post_update(tg, update(3, f"@{BOT.username}"))
    assert [s.text for s in sender.sent] == ["напиши вопрос после /ask"] * 2
    assert rec.seen == []


async def test_group_link_by_non_admin_is_refused(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    sender.admins.clear()
    await link(tg, code, 1)
    assert sender.sent[-1].text == "only chat admins can link"
    assert await db_fetch("SELECT 1 FROM tg_chats") == []
    assert len(await db_fetch("SELECT 1 FROM link_codes")) == 1  # code not burnt


async def test_private_link_needs_no_admin(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    sender.admins.clear()
    await link(tg, code, 1, chat_id=42)
    assert sender.sent[-1].text == "connected"


async def test_long_reply_is_split_and_only_first_chunk_replies(tg, sender, agent) -> None:
    await linked(tg, sender)
    with agent.override(model=FunctionModel(Recorder("a" * 4096 + "b" * 10))):
        await post_update(tg, update(2, "/ask hi"))
    assert [len(s.text) for s in sender.sent] == [4096, 10]
    assert [s.reply_to for s in sender.sent] == [20, None]


async def test_invalid_bot_token_disables_telegram_but_app_starts(postgres_url, agent) -> None:
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        telegram_bot_token=SecretStr("not-a-token"),
        telegram_webhook_secret=SecretStr("s"),
    )
    async for c in _client(create_app(settings, agent=agent)):
        assert (await c.get("/health")).status_code == 200
        resp = await c.post("/api/v1/telegram/webhook", json=update(1, "x"))
        assert resp.status_code == 404


async def test_runner_limits_concurrent_updates() -> None:
    running = peak = 0

    async def process(_: Update) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    runner = UpdateRunner(process, max_concurrent=2)
    for i in range(1, 6):
        runner.submit(Update.model_validate(update(i, "x")))
    await runner.drain()
    assert peak == 2


def test_settings_default_concurrency_and_url_field() -> None:
    s = Settings(_env_file=None, database_url="x", telegram_webhook_url="https://h.test/hook")
    assert (s.telegram_max_concurrent_updates, s.telegram_webhook_url) == (
        8,
        "https://h.test/hook",
    )


def test_webhook_secret_must_match_telegram_charset() -> None:
    for bad in ("has space", "", "x" * 257, "uni-é"):
        with raises(ValidationError):
            Settings(_env_file=None, database_url="x", telegram_webhook_secret=SecretStr(bad))
    ok = Settings(_env_file=None, database_url="x", telegram_webhook_secret=SecretStr("a-Z_9"))
    assert ok.telegram_webhook_secret is not None


def test_channels_do_not_import_the_http_layer() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "channels"
    offenders = [p.name for p in root.rglob("*.py") if "app.api" in p.read_text()]
    assert offenders == []


async def test_message_starting_with_another_mention_still_reaches_us(tg, sender, agent) -> None:
    await linked(tg, sender)
    with agent.override(model=FunctionModel(Recorder("ok"))):
        await post_update(tg, update(2, f"@someone look, @{BOT.username} help"))
    assert [s.text for s in sender.sent] == ["ok"]
