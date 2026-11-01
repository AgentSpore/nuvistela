from fastapi import APIRouter, Response

from app.api.v1.deps import FunnelServiceDep
from app.schemas.funnel import LandingEventRequest, WaitlistRequest

router = APIRouter(prefix="/api/v1")


@router.post("/waitlist")
async def join_waitlist(body: WaitlistRequest, service: FunnelServiceDep) -> dict[str, bool]:
    await service.join_waitlist(body)
    return {"ok": True}


@router.post("/events", status_code=204)
async def landing_event(body: LandingEventRequest, service: FunnelServiceDep) -> Response:
    await service.record_landing_view(body)
    return Response(status_code=204)
