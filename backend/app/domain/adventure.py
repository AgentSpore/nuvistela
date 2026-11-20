from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

TITLE_MAX = 80
QUEST_DESCRIPTION_MAX = 400
SKILL_MAX = 40
REACTION_MAX = 280
MILESTONE_MAX = 80
RECENT_KINDS = 3  # how many latest quests' kinds are loaded to choose the next quest kind
RECENT_SKILLS = 8  # how many latest distinct skills the chapter prompt lists to avoid repeats

QuestKind = Literal["say", "make", "move", "care", "find", "gift"]
Beat = Literal["opening", "turn", "milestone", "develop"]

# Rotation order of `next_quest_kind`. No kind is forbidden for any audience: the age and safety
# limits (move: never climbing or water; 3-5: no cords, fire, climbing, water) live in the quest
# text rules, so every kind stays available.
QUEST_KINDS: tuple[QuestKind, ...] = ("say", "make", "move", "care", "find", "gift")
_KIND_MEMORY = 2  # the kinds of the last quests the next one must differ from

# From chapter 2 the story cycles turn, milestone, develop; the code keeps the rhythm, the model
# only fills it with content.
_CYCLE: tuple[Beat, ...] = ("turn", "milestone", "develop")


def beat_of(chapter_number: int) -> Beat:
    """The story beat of a chapter: 1 opens, then turn(2), milestone(3), develop(4), turn(5)..."""
    return "opening" if chapter_number <= 1 else _CYCLE[(chapter_number - 2) % len(_CYCLE)]


GROWTH_COVER_EVERY = 2  # every 2nd milestone (the 2nd, 4th, 6th...) gives the world a new cover


def milestone_number(chapter_number: int) -> int | None:
    """The ordinal of a milestone chapter (1, 2, 3...), None for any other beat."""
    if beat_of(chapter_number) != "milestone":
        return None
    return (chapter_number - 2) // len(_CYCLE) + 1


def growth_cover_milestone(chapter_number: int) -> int | None:
    """The milestone ordinal when this chapter's milestone earns a new cover, else None."""
    number = milestone_number(chapter_number)
    return number if number and number % GROWTH_COVER_EVERY == 0 else None


def next_quest_kind(recent_kinds: Sequence[str], chapter_number: int) -> QuestKind:
    """The next quest kind: never one of the last two, rotation starting at the chapter number."""
    banned = set(recent_kinds[-_KIND_MEMORY:])
    start = chapter_number % len(QUEST_KINDS)
    ordered = QUEST_KINDS[start:] + QUEST_KINDS[:start]
    return next(kind for kind in ordered if kind not in banned)


def normalize_skill(skill: str) -> str:
    """Trim and lowercase the first letter, unless the second is uppercase (an acronym)."""
    skill = skill.strip()
    if skill[1:2].isupper():
        return skill
    return skill[:1].lower() + skill[1:]


QuestSource = Literal["template", "model", "world"]
QuestStatus = Literal["open", "done"]
ChapterStatus = Literal["queued", "writing", "ready", "delayed_model", "delayed_budget"]


# A quest as stored: the chapter's next quest or the world's first quest. A comment,
# not a docstring: a docstring would become the JSON-schema description sent to the models.
class StoredQuest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    description: str = Field(min_length=1, max_length=QUEST_DESCRIPTION_MAX)
    skill: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SKILL_MAX)
    ]
    reaction: str | None = Field(default=None, min_length=1, max_length=REACTION_MAX)
    kind: QuestKind | None = None  # worlds and quests stored before kinds existed have none


# The same quest as the model must write it: reaction and kind required. `StoredQuest` reads worlds
# stored before reactions existed.
class NextQuest(StoredQuest):
    reaction: str = Field(min_length=1, max_length=REACTION_MAX)  # ty: ignore[invalid-mutable-override]  # narrowing
    kind: QuestKind  # ty: ignore[invalid-mutable-override]  # narrowing


@dataclass(frozen=True)
class Quest:
    id: UUID
    family_id: UUID
    member_id: UUID | None
    seq: int
    title: str
    description: str
    skill: str
    source: QuestSource
    status: QuestStatus
    reaction: str | None
    kind: QuestKind | None


@dataclass(frozen=True)
class QuestDraft:
    title: str
    description: str
    skill: str
    source: QuestSource
    reaction: str | None = None
    kind: QuestKind | None = None


@dataclass(frozen=True)
class QuestEvent:
    id: int
    quest_id: UUID
    member_id: UUID | None
    note: str | None
    idem_key: str | None


@dataclass(frozen=True)
class Chapter:
    id: UUID
    quest_id: UUID
    seq: int
    status: ChapterStatus
    title: str | None
    body: str | None
    summary: str | None
    job_id: UUID | None
    next_run_at: datetime | None
    milestone: str | None  # what changed in the world on a milestone chapter, else None


@dataclass(frozen=True)
class ChapterText:
    """What the model wrote for a chapter, as stored when it becomes ready."""

    title: str
    body: str
    summary: str
    milestone: str | None


@dataclass(frozen=True)
class Adventure:
    quest: Quest | None
    chapters: list[Chapter]
    skills: list[str] = field(default_factory=list)  # of done quests, first appearance order


@dataclass(frozen=True)
class QuestContext:
    """What the chapter prompt needs about a done quest; no previous summary on the first."""

    title: str
    description: str
    member_id: UUID | None
    note: str | None
    reaction: str | None  # what the player already saw when marking the quest done
    previous_summary: str | None
    age_bands: tuple[str, ...]  # of every member of the family, in joining order
    recent_kinds: tuple[QuestKind, ...] = ()  # of the last quests up to this one, oldest first
    recent_skills: tuple[str, ...] = ()  # distinct (by case), up to RECENT_SKILLS, latest first
