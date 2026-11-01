"""WorldSummaryReader for the game master: a short description of the family's ready world."""

from uuid import UUID

from app.repositories.family_repository import FamilyRepository
from app.repositories.world_repository import WorldRepository


class SqlWorldSummary:
    def __init__(self, families: FamilyRepository, worlds: WorldRepository) -> None:
        self._families, self._worlds = families, worlds

    async def summary(self, family_id: str) -> str | None:
        fid = UUID(family_id)
        stored = await self._worlds.get(fid)
        if stored is None or stored.world is None or stored.status == "pending":
            return None
        world = stored.world
        names = {m.id: m.display_name for m in await self._families.list_members(fid)}
        heroes = "; ".join(
            f"{names.get(h.member_id, '?')}: {h.hero_class} ({h.trait}, skill {h.skill})"
            for h in world.heroes
        )
        return (
            f"The family's world: {world.title}. {world.setting}. Tone: {world.tone}. "
            f"Places: {', '.join(loc.name for loc in world.locations)}. Heroes: {heroes}."
        )
