import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from pydantic_ai import Agent

from app.agent.deps import GameDeps
from app.channels.telegram.runner import UpdateRunner
from app.channels.telegram.sender import BotIdentity
from app.core.config import Settings
from app.main import create_app
from tests.conftest import _client

SECRET = "hook-secret"
BOT = BotIdentity(id=777, username="BumbliBot")
HEADER = "X-Telegram-Bot-Api-Secret-Token"


@dataclass
class Sent:
    chat_id: int
    text: str
    reply_to: int | None


class FakeSender:
    """Intercepts every outgoing Telegram call: tests never reach the network."""

    def __init__(self) -> None:
        self.sent: list[Sent] = []
        self.admins: set[int] = {5}  # the default sender of `update()`

    async def chat_member_status(self, chat_id: int, user_id: int) -> str:
        return "administrator" if user_id in self.admins else "member"

    async def me(self) -> BotIdentity:
        return BOT

    async def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        self.sent.append(Sent(chat_id, text, reply_to))


@pytest.fixture(autouse=True)
async def clean_links(db_fetch) -> None:
    """Chat ids repeat across tests and the database is session-wide."""
    await db_fetch("DELETE FROM tg_chats RETURNING 1")
    await db_fetch("DELETE FROM link_codes RETURNING 1")


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
async def tg(
    postgres_url: str, agent: Agent[GameDeps, str], sender: FakeSender
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        database_url=postgres_url,
        cookie_secure=False,
        telegram_bot_token=SecretStr("1:tok"),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    app = create_app(settings, agent=agent, telegram_sender=sender)
    async for c in _client(app):
        yield c


@pytest.fixture
async def tg_off(postgres_url: str, agent: Agent[GameDeps, str]) -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, database_url=postgres_url, cookie_secure=False)
    async for c in _client(create_app(settings, agent=agent)):
        yield c


def runner_of(client: AsyncClient) -> UpdateRunner:
    app = cast(FastAPI, cast(ASGITransport, client._transport).app)
    return app.state.telegram.runner


def update(update_id: int, text: str, chat_id: int = -100, **message) -> dict:
    """Raw Telegram Update JSON for a text message in a group (private when chat_id > 0)."""
    chat_type = "private" if chat_id > 0 else "supergroup"
    body = {
        "message_id": update_id * 10,
        "date": 1,
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": 5, "is_bot": False, "first_name": "Pa"},
        "text": text,
    } | message
    if "entities" not in body:  # Telegram marks every @username of the text as an entity
        body["entities"] = [
            {"type": "mention", "offset": m.start(), "length": len(m.group())}
            for m in re.finditer(r"@\w+", text)
        ]
    return {"update_id": update_id, "message": body}


async def post_update(client: AsyncClient, payload: dict, secret: str | None = SECRET):
    headers = {HEADER: secret} if secret is not None else {}
    resp = await client.post("/api/v1/telegram/webhook", json=payload, headers=headers)
    await runner_of(client).drain()
    return resp
