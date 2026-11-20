from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.api.client_ip import client_ip
from app.api.v1.deps import SESSION_COOKIE, CurrentMember, FamilyServiceDep, PilotServiceDep
from app.domain.errors import AdmissionRefused
from app.schemas.family import (
    AcceptInviteRequest,
    AddMemberRequest,
    CreateFamilyRequest,
    FamilyCreatedResponse,
    InviteResponse,
    MemberResponse,
)
from app.services.family_service import FamilyService

router = APIRouter(prefix="/api/v1")


def _invite_url(token: str, locale: str) -> str:
    """Fragment: never sent to a server or logged. ru is the default locale, so it has no prefix."""
    prefix = "" if locale == "ru" else f"/{locale}"
    return f"{prefix}/join#{token}"


def _set_session_cookie(response: Response, request: Request, session: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session,
        max_age=int(FamilyService.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )


async def admit_new_family(request: Request, service: FamilyServiceDep) -> None:
    state = request.app.state
    await service.require_daily_capacity(
        state.settings.max_new_families_per_day, state.erased_today.count()
    )
    if not request.app.state.family_limiter.allow(client_ip(request)):
        raise AdmissionRefused("rate_limited")


async def admit_invite_accept(request: Request) -> None:
    if not request.app.state.invite_limiter.allow(client_ip(request)):
        raise AdmissionRefused("rate_limited")


@router.post("/families", status_code=201, dependencies=[Depends(admit_new_family)])
async def create_family(
    body: CreateFamilyRequest,
    request: Request,
    response: Response,
    service: FamilyServiceDep,
    pilot: PilotServiceDep,
) -> FamilyCreatedResponse:
    """With pilot attribution the family also counts as a lead; a failed lead keeps the family."""
    family, member, token, session = await service.create_family(
        body.title, body.locale, body.display_name, tuple(body.interests)
    )
    if body.attribution is not None:
        await pilot.record_lead_isolated(body.attribution, body.locale)
    _set_session_cookie(response, request, session)
    return FamilyCreatedResponse(
        family_id=family.id,
        member=MemberResponse.of(member),
        invite_url=_invite_url(token, family.locale),
    )


@router.delete("/families/{family_id}", status_code=204)
async def delete_family(
    family_id: UUID,
    request: Request,
    response: Response,
    actor: CurrentMember,
    service: FamilyServiceDep,
) -> None:
    if await service.delete_family(actor, family_id):
        request.app.state.erased_today.add()
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )


@router.post("/families/{family_id}/members", status_code=201)
async def add_member(
    family_id: UUID, body: AddMemberRequest, actor: CurrentMember, service: FamilyServiceDep
) -> InviteResponse:
    member, token = await service.add_member(actor, family_id, body.to_domain())
    locale = await service.family_locale(family_id)
    return InviteResponse(member=MemberResponse.of(member), invite_url=_invite_url(token, locale))


@router.get("/families/{family_id}/members")
async def list_members(
    family_id: UUID, actor: CurrentMember, service: FamilyServiceDep
) -> list[MemberResponse]:
    return [MemberResponse.of(m) for m in await service.list_members(actor, family_id)]


@router.post("/members/{member_id}/invite")
async def reissue_invite(
    member_id: UUID, actor: CurrentMember, service: FamilyServiceDep
) -> dict[str, str]:
    token = await service.reissue_invite(actor, member_id)
    return {"invite_url": _invite_url(token, await service.family_locale(actor.family_id))}


@router.post("/invite/accept", dependencies=[Depends(admit_invite_accept)])
async def accept_invite(
    body: AcceptInviteRequest, request: Request, response: Response, service: FamilyServiceDep
) -> MemberResponse:
    member, session = await service.accept_invite(body.token)
    response.headers["Referrer-Policy"] = "no-referrer"
    _set_session_cookie(response, request, session)
    return MemberResponse.of(member)


@router.get("/me")
async def me(member: CurrentMember) -> MemberResponse:
    return MemberResponse.of(member)
