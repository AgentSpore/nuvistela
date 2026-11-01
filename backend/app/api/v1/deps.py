from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.errors import Unauthorized
from app.domain.family import Member
from app.repositories.family_repository import FamilyRepository
from app.repositories.funnel_repository import FunnelRepository
from app.services.agent_gateway import AgentGateway
from app.services.family_service import FamilyService
from app.services.funnel_service import FunnelService
from app.services.gateway_factory import build_agent_gateway

SESSION_COOKIE = "bumbli_session"


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """One transaction per request: commit on success, roll back on error."""
    async with request.app.state.engine.begin() as conn:
        yield conn


# scope="function": commit runs before the response is sent, so a client holding
# a 201 can always see the rows (default "request" scope commits after sending).
def get_funnel_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> FunnelService:
    return FunnelService(FunnelRepository(conn))


FunnelServiceDep = Annotated[FunnelService, Depends(get_funnel_service, scope="function")]


def get_family_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
    funnel: FunnelServiceDep,
) -> FamilyService:
    return FamilyService(FamilyRepository(conn), funnel)


FamilyServiceDep = Annotated[FamilyService, Depends(get_family_service)]


async def current_member(
    service: FamilyServiceDep,
    funnel: FunnelServiceDep,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    if not session:
        raise Unauthorized("not authenticated")
    member = await service.authenticate(session)
    await funnel.note_activity(member)
    return member


CurrentMember = Annotated[Member, Depends(current_member)]


def get_agent_gateway(
    request: Request, conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")]
) -> AgentGateway:
    return build_agent_gateway(request.app.state, conn)


AgentGatewayDep = Annotated[AgentGateway, Depends(get_agent_gateway)]
