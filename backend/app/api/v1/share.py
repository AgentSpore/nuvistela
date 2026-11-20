from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.v1.deps import CurrentMember, PilotServiceDep, get_conn
from app.repositories.family_repository import FamilyRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.share_repository import ShareRepository
from app.repositories.world_repository import WorldRepository
from app.schemas.share import PublicShare, ShareCreated, ShareState
from app.services.share_service import ShareService

router = APIRouter(prefix="/api/v1")

# Short: a revoked link must stop working within minutes (the private media cache lasts a year).
PUBLIC_CACHE_CONTROL = "public, max-age=300"


def get_share_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")], request: Request
) -> ShareService:
    return ShareService(
        FamilyRepository(conn),
        WorldRepository(conn),
        ImageRepository(conn),
        ShareRepository(conn),
        request.app.state.settings.share_token_key,
    )


ShareServiceDep = Annotated[ShareService, Depends(get_share_service)]


@router.post("/families/{family_id}/world/share")
async def create_share(
    family_id: UUID, actor: CurrentMember, service: ShareServiceDep, pilot: PilotServiceDep
) -> ShareCreated:
    link = await service.create(actor, family_id)
    if link.created:
        await pilot.record_share("share_created")
    return ShareCreated.of(link)


@router.get("/families/{family_id}/world/share")
async def share_state(
    family_id: UUID, actor: CurrentMember, service: ShareServiceDep
) -> ShareState:
    return ShareState.of(await service.status(actor, family_id))


@router.delete("/families/{family_id}/world/share", status_code=204)
async def revoke_share(
    family_id: UUID, actor: CurrentMember, service: ShareServiceDep, pilot: PilotServiceDep
) -> None:
    if await service.revoke(actor, family_id):
        await pilot.record_share("share_revoked")


@router.get("/share/{token}")
async def get_share(token: str, service: ShareServiceDep) -> PublicShare:
    return PublicShare.of(await service.public(token), token)


@router.get(
    "/share/{token}/cover.webp",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}}}},
)
async def get_share_cover(token: str, service: ShareServiceDep) -> Response:
    data = await service.cover(token)
    return Response(data, media_type="image/webp", headers={"Cache-Control": PUBLIC_CACHE_CONTROL})
