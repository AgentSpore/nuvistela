from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.domain.adventure import Adventure, Chapter, ChapterStatus, Quest, QuestSource, QuestStatus
from app.repositories.world_repository import WorldStatus
from app.services.adventure_service import AdventureView


class WorldState(BaseModel):
    status: WorldStatus


class QuestOut(BaseModel):
    id: UUID
    seq: int
    title: str
    description: str
    skill: str
    source: QuestSource
    status: QuestStatus
    reaction: str | None

    @classmethod
    def of(cls, quest: Quest) -> Self:
        return cls(**{f: getattr(quest, f) for f in cls.model_fields})


class ChapterOut(BaseModel):
    id: UUID
    seq: int
    status: ChapterStatus
    title: str | None
    body: str | None
    milestone: str | None

    @classmethod
    def of(cls, chapter: Chapter) -> Self:
        return cls(**{f: getattr(chapter, f) for f in cls.model_fields})


class ChronicleEntry(BaseModel):
    chapter: int
    text: str


class ChapterRef(BaseModel):
    id: UUID
    status: ChapterStatus


class AdventureStarted(BaseModel):
    world_status: WorldStatus | None
    quest: QuestOut | None


class AdventureResponse(BaseModel):
    world: WorldState | None
    quest: QuestOut | None
    chapters: list[ChapterOut]
    chronicle: list[ChronicleEntry]  # quality-gate: field-read-externally (G2 world card)
    skills: list[str]  # of done quests, in order of first appearance

    @classmethod
    def of(cls, view: AdventureView) -> Self:
        adventure: Adventure = view.adventure
        return cls(
            world=None if view.world_status is None else WorldState(status=view.world_status),
            quest=None if adventure.quest is None else QuestOut.of(adventure.quest),
            chapters=[ChapterOut.of(c) for c in adventure.chapters],
            chronicle=[
                ChronicleEntry(chapter=c.seq, text=c.milestone)
                for c in adventure.chapters
                if c.milestone
            ],
            skills=adventure.skills,
        )


class DoneRequest(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=280)] | None = None


class DoneResponse(BaseModel):
    chapter: ChapterRef
    next_quest: QuestOut | None = None  # the model writes it with the chapter (S3)
