"""FamilyStateReader port for the game master, backed by the family repository."""

from uuid import UUID

from app.agent.deps import FamilyStateView
from app.repositories.family_repository import FamilyRepository


class SqlFamilyState:
    def __init__(self, repo: FamilyRepository) -> None:
        self._repo = repo

    async def get_state(self, family_id: str) -> FamilyStateView:
        fid = UUID(family_id)
        family = await self._repo.get_family(fid)
        members = await self._repo.list_members(fid)
        return FamilyStateView(
            family_title=family.title if family else "",
            member_names=tuple(m.display_name for m in members),
        )
