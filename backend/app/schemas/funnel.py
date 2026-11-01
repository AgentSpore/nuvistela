from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.family import AgeBand

Locale = Literal["ru", "en"]
KidsBand = Literal[AgeBand.B3_5, AgeBand.B6_9, AgeBand.B10_13, AgeBand.B14_17]


class WaitlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        ),
    ]
    family_size: Annotated[int, Field(ge=1, le=12)]
    kids_age_bands: Annotated[list[KidsBand], Field(max_length=4)] = []
    locale: Locale = "ru"

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()

    @field_validator("kids_age_bands")
    @classmethod
    def _unique_sorted(cls, value: list[AgeBand]) -> list[AgeBand]:
        return sorted(set(value), key=list(AgeBand).index)


class LandingEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["landing_view"]
    locale: Locale | None = None
    utm_source: Annotated[str, StringConstraints(max_length=64, pattern=r"^[\w.\-]+$")] | None = (
        None
    )
