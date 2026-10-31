from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AgeBand(StrEnum):
    B3_5 = "3-5"
    B6_9 = "6-9"
    B10_13 = "10-13"
    B14_17 = "14-17"
    ADULT = "adult"


class Role(StrEnum):
    ADULT = "adult"
    CHILD = "child"


@dataclass(frozen=True)
class Family:
    id: UUID
    title: str
    locale: str
    created_at: datetime


@dataclass(frozen=True)
class Member:
    id: UUID
    family_id: UUID
    display_name: str
    age_band: AgeBand
    role: Role
    interests: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class NewMember:
    display_name: str
    age_band: AgeBand
    role: Role
    interests: tuple[str, ...] = ()
