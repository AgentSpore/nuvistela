from uuid import UUID

from fastapi import APIRouter

from app.api.v1.deps import CurrentMember, WorldServiceDep
from app.schemas.world import WorldRequest, WorldResponse
from app.services.world_service import WorldForm

router = APIRouter(prefix="/api/v1")


@router.post("/families/{family_id}/world", status_code=202)
async def create_world(
    family_id: UUID, body: WorldRequest, actor: CurrentMember, service: WorldServiceDep
) -> WorldResponse:
    return WorldResponse.of(await service.request(actor, family_id, body.to_form()))


@router.post("/families/{family_id}/world/regenerate", status_code=202)
async def regenerate_world(
    family_id: UUID, actor: CurrentMember, service: WorldServiceDep
) -> WorldResponse:
    return WorldResponse.of(await service.request(actor, family_id, WorldForm()))


@router.get("/families/{family_id}/world")
async def get_world(
    family_id: UUID, actor: CurrentMember, service: WorldServiceDep
) -> WorldResponse:
    return WorldResponse.of(await service.get(actor, family_id))
