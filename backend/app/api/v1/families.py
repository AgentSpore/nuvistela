from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.deps import SESSION_COOKIE, CurrentMember, FamilyServiceDep
from app.domain.errors import Forbidden, NotFound, Unauthorized
from app.schemas.family import (
    AddMemberRequest,
    CreateFamilyRequest,
    FamilyCreatedResponse,
    InviteResponse,
    MemberResponse,
)

router = APIRouter(prefix="/api/v1")

SESSION_MAX_AGE_S = 365 * 24 * 3600


def _invite_url(token: str) -> str:
    return f"/api/v1/invite/{token}"


def register_error_handlers(app: FastAPI) -> None:
    for exc, status, detail in (
        (Unauthorized, 401, "not authenticated"),
        (Forbidden, 403, "adults only"),
        (NotFound, 404, "not found"),
    ):

        def handler(_: Request, __: Exception, status: int = status, detail: str = detail):
            return JSONResponse({"detail": detail}, status_code=status)

        app.add_exception_handler(exc, handler)


@router.post("/families", status_code=201)
async def create_family(
    body: CreateFamilyRequest, service: FamilyServiceDep
) -> FamilyCreatedResponse:
    family, member, token = await service.create_family(
        body.title, body.locale, body.display_name, tuple(body.interests)
    )
    return FamilyCreatedResponse(
        family_id=family.id, member=MemberResponse.of(member), invite_url=_invite_url(token)
    )


@router.post("/families/{family_id}/members", status_code=201)
async def add_member(
    family_id: UUID, body: AddMemberRequest, actor: CurrentMember, service: FamilyServiceDep
) -> InviteResponse:
    member, token = await service.add_member(actor, family_id, body.to_domain())
    return InviteResponse(member=MemberResponse.of(member), invite_url=_invite_url(token))


@router.post("/members/{member_id}/invite")
async def reissue_invite(
    member_id: UUID, actor: CurrentMember, service: FamilyServiceDep
) -> dict[str, str]:
    return {"invite_url": _invite_url(await service.reissue_invite(actor, member_id))}


@router.get("/invite/{token}")
async def accept_invite(
    token: str, request: Request, service: FamilyServiceDep
) -> RedirectResponse:
    try:
        await service.authenticate(token)
    except Unauthorized:
        raise HTTPException(status_code=401, detail="invalid invite") from None
    response = RedirectResponse("/play", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_S,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/me")
async def me(member: CurrentMember) -> MemberResponse:
    return MemberResponse.of(member)
