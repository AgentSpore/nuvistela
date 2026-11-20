"""The template quest that keeps the game going while a chapter is delayed."""

from uuid import UUID

from app.domain.adventure import QuestDraft
from app.domain.quest_templates import template_quest
from app.domain.world import World
from app.domain.world_fallback import fallback_world
from app.repositories.adventure_repository import AdventureRepository


async def open_fallback_quest(
    adventures: AdventureRepository, family_id: UUID, member_id: UUID | None, locale: str
) -> None:
    """Open the template for the family's next quest number; a no-op while one is open."""
    seq = await adventures.next_quest_seq(family_id)
    await adventures.open_quest(family_id, member_id, template_quest(locale, seq))


def first_quest_draft(world: World, locale: str) -> QuestDraft:
    """Quest 1: the world's own `first_quest`, or the template when the world has none."""
    quest = world.first_quest
    if quest is None:
        return template_quest(locale, 1)
    return QuestDraft(
        quest.title, quest.description, quest.skill, "world", quest.reaction, quest.kind
    )


def fallback_world_and_quest(
    genre: str, locale: str, member_ids: list[UUID]
) -> tuple[World, QuestDraft]:
    """The stored world of a family that cannot get a generated one, and its quest 1."""
    world = fallback_world(genre, locale, member_ids)
    return world, first_quest_draft(world, locale)
