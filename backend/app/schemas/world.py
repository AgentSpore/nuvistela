from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, StringConstraints, model_validator

from app.domain.world import World
from app.repositories.world_repository import StoredWorld, WorldStatus
from app.schemas.family import Interests
from app.services.world_service import WorldForm


class WorldRequest(BaseModel):
    genre: Literal["fairy_tale", "space", "pirates", "custom"]
    custom_genre: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = (
        None
    )
    interests: dict[UUID, Interests] = {}

    @model_validator(mode="after")
    def _custom_needs_text(self) -> Self:
        if (self.genre == "custom") != bool(self.custom_genre):
            raise ValueError("custom_genre is required for genre custom, and only then")
        return self

    def to_form(self) -> WorldForm:
        return WorldForm(
            self.genre, self.custom_genre, {k: tuple(v) for k, v in self.interests.items()}
        )


class WorldResponse(BaseModel):
    status: WorldStatus
    genre: str
    world: World | None

    @classmethod
    def of(cls, stored: StoredWorld) -> Self:
        return cls(status=stored.status, genre=stored.genre, world=stored.world)
