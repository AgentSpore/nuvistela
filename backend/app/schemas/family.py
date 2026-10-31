from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.domain.family import AgeBand, Member, NewMember, Role

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Interest = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Interests = Annotated[list[Interest], Field(max_length=10)]


class CreateFamilyRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    locale: Annotated[str, StringConstraints(pattern="^(ru|en)$")] = "ru"
    display_name: DisplayName
    interests: Interests = []


class AddMemberRequest(BaseModel):
    display_name: DisplayName
    age_band: AgeBand
    role: Role
    interests: Interests = []

    @model_validator(mode="after")
    def _role_matches_age_band(self) -> Self:
        if (self.role is Role.ADULT) != (self.age_band is AgeBand.ADULT):
            raise ValueError("role adult requires age_band adult, and only then")
        return self

    def to_domain(self) -> NewMember:
        return NewMember(self.display_name, self.age_band, self.role, tuple(self.interests))


class MemberResponse(BaseModel):
    id: UUID
    family_id: UUID
    display_name: str
    age_band: AgeBand
    role: Role
    interests: list[str]

    @classmethod
    def of(cls, m: Member) -> Self:
        return cls(
            id=m.id,
            family_id=m.family_id,
            display_name=m.display_name,
            age_band=m.age_band,
            role=m.role,
            interests=list(m.interests),
        )


class AcceptInviteRequest(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class InviteResponse(BaseModel):
    member: MemberResponse
    invite_url: str


class FamilyCreatedResponse(InviteResponse):
    family_id: UUID
