from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.errors import Unauthorized
from app.domain.family import Member
from app.repositories.family_repository import FamilyRepository
from app.services.family_service import FamilyService

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


async def current_member(
    service: FamilyServiceDep,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    if not session:
        raise Unauthorized("not authenticated")
    return await service.authenticate(session)


CurrentMember = Annotated[Member, Depends(current_member)]
