from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, StringConstraints, model_validator

from app.domain.world import World
from app.repositories.image_repository import CoverState, ImageStatus
from app.repositories.world_repository import StoredWorld, WorldStatus
from app.repositories.world_scene_repository import SceneInfo, SceneStatus
from app.schemas.family import Interests
from app.services.world_service import WorldForm


class WorldRequest(BaseModel):
    genre: Literal["fairy_tale", "space", "pirates", "custom"]
    custom_genre: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
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


class CoverResponse(BaseModel):
    status: ImageStatus
    url: str | None  # set only when ready
    deferred: bool = False  # pending until the next UTC day: the daily budget is spent

    @classmethod
    def of(cls, state: CoverState) -> Self:
        url = f"/api/v1/media/{state.sha}.webp" if state.status == "ready" and state.sha else None
        return cls(status=state.status, url=url, deferred=state.deferred)


class SceneResponse(BaseModel):
    status: SceneStatus
    url: str | None  # the .spz, set only when ready
    panorama_url: str | None  # the fallback picture, set only when ready

    @classmethod
    def of(cls, info: SceneInfo) -> Self:
        sha = info.sha if info.status == "ready" else None
        return cls(
            status=info.status,
            url=f"/api/v1/media/{sha}.spz" if sha else None,
            panorama_url=f"/api/v1/media/pano/{sha}.webp" if sha else None,
        )


class WorldResponse(BaseModel):
    status: WorldStatus
    genre: str
    world: World | None
    cover: CoverResponse | None = None
    scene: SceneResponse | None = None
    cover_growing: bool = False  # a newer cover is being made: `cover` is still the previous one

    @classmethod
    def of(
        cls,
        stored: StoredWorld,
        cover: CoverState | None = None,
        scene: SceneInfo | None = None,
        cover_growing: bool = False,
    ) -> Self:
        return cls(
            status=stored.status,
            genre=stored.genre,
            world=stored.world,
            cover=None if cover is None else CoverResponse.of(cover),
            scene=None if scene is None else SceneResponse.of(scene),
            cover_growing=cover_growing,
        )
