import hmac
import logging
from typing import Annotated
from uuid import UUID

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from app.api.v1.deps import CurrentMember
from app.channels.telegram.runner import UpdateRunner
from app.repositories.link_repository import LinkRepository
from app.schemas.telegram import LinkCodeResponse
from app.services.telegram_link import TelegramLinkService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@router.post("/telegram/webhook")
async def webhook(
    request: Request,
    secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> dict[str, bool]:
    telegram = request.app.state.telegram
    if telegram is None:
        raise HTTPException(404)
    expected = request.app.state.settings.telegram_webhook_secret.get_secret_value()
    if secret is None or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(401, "invalid secret")
    try:
        update = Update.model_validate_json(await request.body())
    except ValidationError:
        logger.warning("telegram webhook: malformed update dropped")
        return {"ok": True}  # a non-200 would make Telegram redeliver the same bad update
    runner: UpdateRunner = telegram.runner
    runner.submit(update)
    return {"ok": True}


@router.post("/families/{family_id}/telegram/link-code")
async def issue_link_code(
    family_id: UUID, actor: CurrentMember, request: Request
) -> LinkCodeResponse:
    async with request.app.state.engine.begin() as conn:
        code, expires = await TelegramLinkService(LinkRepository(conn)).issue_code(actor, family_id)
    return LinkCodeResponse(code=code, expires_at=expires)
