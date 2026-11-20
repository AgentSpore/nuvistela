from fastapi import APIRouter, HTTPException, Response

from app.api.v1.deps import FunnelServiceDep, PilotServiceDep
from app.schemas.funnel import LandingEventRequest, WaitlistRequest
from app.schemas.pilot import PilotEventRequest

router = APIRouter(prefix="/api/v1")


@router.post("/waitlist")
async def join_waitlist(body: WaitlistRequest, service: FunnelServiceDep) -> dict[str, bool]:
    await service.join_waitlist(body)
    return {"ok": True}


@router.post("/events", status_code=204)
async def landing_event(body: LandingEventRequest, service: FunnelServiceDep) -> Response:
    await service.record_landing_view(body)
    return Response(status_code=204)


@router.post("/pilot/events", status_code=204)
async def pilot_event(body: PilotEventRequest, service: PilotServiceDep) -> Response:
    if not await service.record(body):
        raise HTTPException(status_code=409, detail="event_id already used for another payload")
    return Response(status_code=204)
