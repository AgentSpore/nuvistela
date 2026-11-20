from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.errors import Unauthorized
from app.domain.family import Member
from app.repositories.adventure_repository import AdventureRepository
from app.repositories.family_repository import FamilyRepository
from app.repositories.funnel_repository import FunnelRepository
from app.repositories.image_repository import ImageRepository
from app.repositories.job_repository import JobRepository
from app.repositories.pilot_repository import PilotRepository
from app.repositories.world_repository import WorldRepository
from app.repositories.world_scene_repository import WorldSceneRepository
from app.services.adventure_service import AdventureService
from app.services.agent_gateway import AgentGateway
from app.services.family_service import FamilyService
from app.services.funnel_service import FunnelService
from app.services.gateway_factory import build_agent_gateway
from app.services.pilot_service import PilotService
from app.services.world_service import WorldService

SESSION_COOKIE = "bumbli_session"


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """One transaction per request: commit on success, roll back on error."""
    async with request.app.state.engine.begin() as conn:
        yield conn
    # Reached only after a successful commit: a rolled-back activity write is retried next time.
    if member_id := getattr(request.state, "activity_member_id", None):
        FunnelService.mark_checked(member_id)


def get_pilot_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> PilotService:
    return PilotService(PilotRepository(conn))


# scope="function": commit runs before the response is sent, so a client holding
# a 201 can always see the rows (default "request" scope commits after sending).
def get_funnel_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
    pilot: Annotated[PilotService, Depends(get_pilot_service, scope="function")],
) -> FunnelService:
    return FunnelService(FunnelRepository(conn), pilot)


FunnelServiceDep = Annotated[FunnelService, Depends(get_funnel_service, scope="function")]


def get_family_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
    funnel: FunnelServiceDep,
) -> FamilyService:
    return FamilyService(FamilyRepository(conn), funnel)


FamilyServiceDep = Annotated[FamilyService, Depends(get_family_service)]


def get_world_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
    request: Request,
) -> WorldService:
    return WorldService(
        FamilyRepository(conn),
        WorldRepository(conn),
        JobRepository(conn),
        ImageRepository(conn),
        world_available=request.app.state.world_worker is not None,
    )


WorldServiceDep = Annotated[WorldService, Depends(get_world_service)]


def get_adventure_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
    worlds: WorldServiceDep,
    request: Request,
) -> AdventureService:
    return AdventureService(
        FamilyRepository(conn),
        AdventureRepository(conn),
        JobRepository(conn),
        worlds,
        world_available=request.app.state.world_worker is not None,
    )


AdventureServiceDep = Annotated[AdventureService, Depends(get_adventure_service)]


async def current_member(
    service: FamilyServiceDep,
    funnel: FunnelServiceDep,
    request: Request,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    if not session:
        raise Unauthorized("not authenticated")
    member = await service.authenticate(session)
    await funnel.note_activity(member)
    request.state.activity_member_id = member.id
    return member


CurrentMember = Annotated[Member, Depends(current_member)]


async def member_or_none(
    service: FamilyServiceDep,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member | None:
    """The signed-in member, None for an anonymous or unknown session (no activity is noted)."""
    if not session:
        return None
    try:
        return await service.authenticate(session)
    except Unauthorized:
        return None


OptionalMember = Annotated[Member | None, Depends(member_or_none)]


def get_image_repository(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> ImageRepository:
    return ImageRepository(conn)


ImageRepositoryDep = Annotated[ImageRepository, Depends(get_image_repository)]


def get_world_scene_repository(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> WorldSceneRepository:
    return WorldSceneRepository(conn)


WorldSceneRepositoryDep = Annotated[WorldSceneRepository, Depends(get_world_scene_repository)]


def get_agent_gateway(
    request: Request, conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")]
) -> AgentGateway:
    return build_agent_gateway(request.app.state, conn)


AgentGatewayDep = Annotated[AgentGateway, Depends(get_agent_gateway)]


PilotServiceDep = Annotated[PilotService, Depends(get_pilot_service, scope="function")]
