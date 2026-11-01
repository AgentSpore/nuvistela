from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.errors import Unauthorized
from app.domain.family import Member
from app.repositories.family_repository import FamilyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.world_repository import WorldRepository
from app.services.agent_gateway import AgentGateway
from app.services.family_service import FamilyService
from app.services.gateway_factory import build_agent_gateway
from app.services.world_service import WorldService

SESSION_COOKIE = "bumbli_session"


async def get_conn(request: Request) -> AsyncIterator[AsyncConnection]:
    """One transaction per request: commit on success, roll back on error."""
    async with request.app.state.engine.begin() as conn:
        yield conn


# scope="function": commit runs before the response is sent, so a client holding
# a 201 can always see the rows (default "request" scope commits after sending).
def get_family_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> FamilyService:
    return FamilyService(FamilyRepository(conn))


FamilyServiceDep = Annotated[FamilyService, Depends(get_family_service)]


def get_world_service(
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> WorldService:
    return WorldService(FamilyRepository(conn), WorldRepository(conn), JobRepository(conn))


WorldServiceDep = Annotated[WorldService, Depends(get_world_service)]


async def current_member(
    service: FamilyServiceDep,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    if not session:
        raise Unauthorized("not authenticated")
    return await service.authenticate(session)


CurrentMember = Annotated[Member, Depends(current_member)]


def get_agent_gateway(
    request: Request, conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")]
) -> AgentGateway:
    return build_agent_gateway(request.app.state, conn)


AgentGatewayDep = Annotated[AgentGateway, Depends(get_agent_gateway)]
