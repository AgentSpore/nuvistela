import asyncio
from datetime import UTC, datetime, timedelta

from pydantic_ai.exceptions import ModelAPIError, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.services.family_service import FamilyService
from tests.telegram.conftest import BOT, post_update, runner_of, update
from tests.test_agent_api import Recorder, make_member

CODE_URL = "/api/v1/families/{}/telegram/link-code"
CHAT = -100


async def issue_code(tg, family_id: str, cookie: dict) -> str:
    return (await tg.post(CODE_URL.format(family_id), headers=cookie)).json()["code"]


async def link(tg, code: str, update_id: int, chat_id: int = CHAT):
    return await post_update(tg, update(update_id, f"/link {code}", chat_id))


async def chat_family(db_fetch, chat_id: int = CHAT) -> str | None:
    rows = await db_fetch("SELECT family_id::text AS f FROM tg_chats WHERE chat_id = $1", chat_id)
    return rows[0]["f"] if rows else None


async def test_wrong_secret_is_401_and_nothing_processed(tg, sender) -> None:
    resp = await post_update(tg, update(1, "/link X"), secret="nope")
    assert resp.status_code == 401
    assert sender.sent == []


async def test_missing_secret_is_401(tg, sender) -> None:
    assert (await post_update(tg, update(1, "/link X"), secret=None)).status_code == 401
    assert sender.sent == []


async def test_unconfigured_telegram_is_404_and_app_runs(tg_off) -> None:
    resp = await tg_off.post("/api/v1/telegram/webhook", json=update(1, "hi"))
    assert resp.status_code == 404
    assert (await tg_off.get("/health")).status_code == 200


async def test_link_with_valid_code_binds_chat(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    resp = await link(tg, code, 1)
    assert resp.status_code == 200
    assert await chat_family(db_fetch) == family_id
    assert [s.text for s in sender.sent] == ["connected"]
    assert sender.sent[0].reply_to == 10


async def test_link_accepts_lowercase_code(tg, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    await link(tg, code.lower(), 1)
    assert await chat_family(db_fetch) == family_id


async def test_used_code_is_rejected(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    await link(tg, code, 1)
    await link(tg, code, 2, chat_id=-200)
    assert sender.sent[-1].text == "code invalid or expired"
    assert await chat_family(db_fetch, -200) is None


async def test_expired_code_is_rejected(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    await db_fetch(
        "UPDATE link_codes SET expires_at = $1 WHERE code_hash = $2 RETURNING 1",
        datetime.now(UTC) - timedelta(seconds=1),
        FamilyService.hash_token(code),
    )
    await link(tg, code, 1)
    assert sender.sent[-1].text == "code invalid or expired"
    assert await chat_family(db_fetch) is None


async def test_unknown_and_empty_code_get_fixed_reply(tg, sender) -> None:
    await link(tg, "ZZZZZZZZ", 1)
    await post_update(tg, update(2, "/link"))
    assert [s.text for s in sender.sent] == ["code invalid or expired"] * 2


async def test_relink_to_other_family_replaces_binding(tg, db_fetch) -> None:
    cookie_a, fam_a = await make_member(tg, "A")
    cookie_b, fam_b = await make_member(tg, "B")
    await link(tg, await issue_code(tg, fam_a, cookie_a), 1)
    await link(tg, await issue_code(tg, fam_b, cookie_b), 2)
    assert await chat_family(db_fetch) == fam_b


async def test_code_of_family_a_never_binds_chat_to_family_b(tg, db_fetch) -> None:
    cookie_a, fam_a = await make_member(tg, "A")
    _, fam_b = await make_member(tg, "B")
    await link(tg, await issue_code(tg, fam_a, cookie_a), 1)
    assert await chat_family(db_fetch) == fam_a != fam_b


async def test_two_concurrent_links_with_one_code_bind_exactly_once(tg, sender, db_fetch) -> None:
    cookie, family_id = await make_member(tg)
    code = await issue_code(tg, family_id, cookie)
    bodies = [update(1, f"/link {code}", -301), update(2, f"/link {code}", -302)]
    await asyncio.gather(
        *(
            tg.post(
                "/api/v1/telegram/webhook",
                json=b,
                headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
            )
            for b in bodies
        )
    )
    await runner_of(tg).drain()
    bound = [await chat_family(db_fetch, c) for c in (-301, -302)]
    assert sorted(b is not None for b in bound) == [False, True]
    assert sorted(s.text for s in sender.sent) == ["code invalid or expired", "connected"]


async def test_duplicate_update_id_is_processed_once(tg, sender) -> None:
    payload = update(1, f"@{BOT.username} hi")
    await post_update(tg, payload)
    resp = await post_update(tg, payload)
    assert resp.status_code == 200
    assert len(sender.sent) == 1


async def test_unlinked_chat_addressing_bot_gets_link_hint(tg, sender) -> None:
    await post_update(tg, update(1, f"@{BOT.username} hello"))
    assert [s.text for s in sender.sent] == ["link this chat first: /link <code> from the site"]


async def test_message_not_addressed_to_bot_is_ignored(tg, sender, agent) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, "just family chatter"))
    assert sender.sent == [] and rec.seen == []


async def test_mention_in_linked_chat_goes_to_agent_and_replies(
    tg, sender, agent, db_fetch
) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()
    rec = Recorder("Hello, Smiths")
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, f"@{BOT.username} what now?"))
    assert [(s.text, s.reply_to) for s in sender.sent] == [("Hello, Smiths", 20)]
    assert rec.prompts() == ["what now?"]
    rows = await db_fetch(
        "SELECT channel, member_id FROM agent_messages WHERE family_id = $1::uuid", family_id
    )
    assert {(r["channel"], r["member_id"]) for r in rows} == {("telegram", None)}


async def test_reply_to_bot_goes_to_agent(tg, sender, agent) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()
    reply_to = {
        "message_id": 1,
        "date": 1,
        "chat": {"id": CHAT, "type": "supergroup"},
        "from": {"id": BOT.id, "is_bot": True, "first_name": "B"},
        "text": "earlier",
    }
    with agent.override(model=FunctionModel(Recorder("ok"))):
        await post_update(tg, update(2, "and then?", reply_to_message=reply_to))
    assert [s.text for s in sender.sent] == ["ok"]


async def test_private_chat_linked_needs_no_mention(tg, sender, agent) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1, chat_id=42)
    sender.sent.clear()
    with agent.override(model=FunctionModel(Recorder("pm-ok"))):
        await post_update(tg, update(2, "hello", chat_id=42))
    assert [s.text for s in sender.sent] == ["pm-ok"]


async def test_too_long_text_gets_fixed_reply_and_no_turn(tg, sender, agent) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()
    rec = Recorder()
    with agent.override(model=FunctionModel(rec)):
        await post_update(tg, update(2, f"@{BOT.username} " + "x" * 2001))
    assert [s.text for s in sender.sent] == ["message too long (max 2000 characters)"]
    assert rec.seen == []


async def _linked(tg, sender) -> None:
    cookie, family_id = await make_member(tg)
    await link(tg, await issue_code(tg, family_id, cookie), 1)
    sender.sent.clear()


async def test_budget_exceeded_maps_to_fixed_reply(tg, sender, agent) -> None:
    await _linked(tg, sender)

    def over(messages, info):
        raise UsageLimitExceeded("limit")

    with agent.override(model=FunctionModel(over)):
        await post_update(tg, update(2, f"@{BOT.username} hi"))
    assert [s.text for s in sender.sent] == ["daily limit reached"]


async def test_unavailable_model_maps_to_fixed_reply_without_internals(tg, sender, agent) -> None:
    await _linked(tg, sender)

    def down(messages, info):
        raise ModelAPIError("vendor/model-x", "boom internals")

    with agent.override(model=FunctionModel(down)):
        await post_update(tg, update(2, f"@{BOT.username} hi"))
    assert [s.text for s in sender.sent] == ["game master unavailable"]


async def test_busy_family_maps_to_wait_reply(tg, sender, agent) -> None:
    await _linked(tg, sender)

    async def slow(messages, info):
        await asyncio.sleep(0.4)
        return ModelResponse(parts=[TextPart("done")])

    with agent.override(model=FunctionModel(slow)):
        await tg.post(
            "/api/v1/telegram/webhook",
            json=update(2, f"@{BOT.username} a"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        )
        await asyncio.sleep(0.15)
        await tg.post(
            "/api/v1/telegram/webhook",
            json=update(3, f"@{BOT.username} b"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        )
        await runner_of(tg).drain()
    assert sorted(s.text for s in sender.sent) == ["done", "wait, I'm still answering"]


async def test_shutdown_cancels_unfinished_tasks(tg, sender, agent) -> None:
    await _linked(tg, sender)

    async def hang(messages, info):
        await asyncio.sleep(30)
        return ModelResponse(parts=[TextPart("never")])

    runner = runner_of(tg)
    with agent.override(model=FunctionModel(hang)):
        await tg.post(
            "/api/v1/telegram/webhook",
            json=update(2, f"@{BOT.username} a"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"},
        )
        await asyncio.sleep(0.1)
        await runner.shutdown(grace_s=0.1)
    assert runner.pending == 0
