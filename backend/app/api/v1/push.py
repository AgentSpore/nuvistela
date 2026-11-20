from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.v1.deps import CurrentMember, FunnelServiceDep, get_conn
from app.channels.push.repository import PushRepository
from app.channels.push.schemas import (
    OpenedRequest,
    PublicKeyResponse,
    SubscribeRequest,
    UnsubscribeRequest,
)
from app.core.config import Settings
from app.domain.errors import Forbidden
from app.domain.family import Member, Role
from app.domain.funnel import EventKind

router = APIRouter(prefix="/api/v1/push")

Conn = Annotated[AsyncConnection, Depends(get_conn, scope="function")]


def _require_push(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not settings.push_enabled:
        raise HTTPException(404)
    return settings


def _require_adult(actor: Member) -> None:
    if actor.role is not Role.ADULT:
        raise Forbidden("only adults can manage reminders")


@router.get("/key")
async def public_key(request: Request) -> PublicKeyResponse:
    return PublicKeyResponse(public_key=_require_push(request).vapid_public_key or "")


@router.post("/subscriptions", status_code=201)
async def subscribe(
    body: SubscribeRequest, actor: CurrentMember, request: Request, conn: Conn
) -> Response:
    _require_push(request)
    _require_adult(actor)
    await PushRepository(conn).upsert(
        actor, body.endpoint, body.keys.p256dh, body.keys.auth, body.tz
    )
    return Response(status_code=201)


@router.delete("/subscriptions", status_code=204)
async def unsubscribe(
    body: UnsubscribeRequest, actor: CurrentMember, request: Request, conn: Conn
) -> Response:
    _require_push(request)
    _require_adult(actor)
    await PushRepository(conn).delete_own(actor.id, body.endpoint)
    return Response(status_code=204)


@router.post("/opened", status_code=204)
async def opened(
    body: OpenedRequest, actor: CurrentMember, request: Request, funnel: FunnelServiceDep
) -> Response:
    """The service worker reports a notification click: the kind only, never its text."""
    _require_push(request)
    props = {"kind": body.kind, "channel": "push"}
    await funnel.record_event(EventKind.REMINDER_OPENED, actor.family_id, actor.id, props)
    return Response(status_code=204)
