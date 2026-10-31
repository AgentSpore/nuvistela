from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
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


def get_family_service(conn: Annotated[AsyncConnection, Depends(get_conn)]) -> FamilyService:
    return FamilyService(FamilyRepository(conn))


FamilyServiceDep = Annotated[FamilyService, Depends(get_family_service)]


async def current_member(
    service: FamilyServiceDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Member:
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return await service.authenticate(token)
    except Unauthorized:
        raise HTTPException(status_code=401, detail="not authenticated") from None


CurrentMember = Annotated[Member, Depends(current_member)]
