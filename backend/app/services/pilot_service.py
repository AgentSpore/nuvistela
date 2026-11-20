import logging
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.pilot_repository import PilotRepository
from app.schemas.pilot import (
    PilotAttribution,
    PilotEvent,
    PilotEventRequest,
    PilotLocale,
    ServerShareKind,
)

logger = logging.getLogger(__name__)


class PilotService:
    def __init__(self, repo: PilotRepository) -> None:
        self._repo = repo

    async def record(self, body: PilotEventRequest) -> bool:
        """Record an allowlisted client event without accepting server-only lead events.

        Raises RateLimited past the per-session event cap. Per-IP limits belong to the ingress.
        """
        return await self._repo.add(PilotEvent(**body.model_dump()), enforce_cap=True)

    async def record_lead(self, attribution: PilotAttribution, locale: PilotLocale) -> None:
        """Record a new lead within the caller's waitlist transaction."""
        await self._repo.add(
            PilotEvent(
                **attribution.model_dump(),
                event_id=uuid4(),
                kind="lead_created",
                locale=locale,
            )
        )

    async def record_lead_isolated(
        self, attribution: PilotAttribution, locale: PilotLocale
    ) -> bool:
        """Record a lead in a savepoint so a failed write cannot undo the caller's own rows.

        Returns False (and logs without player data) when the lead was not stored.
        """
        try:
            async with self._repo.savepoint():
                await self.record_lead(attribution, locale)
        except SQLAlchemyError:
            logger.warning("pilot lead not recorded")
            return False
        return True

    async def record_share(self, kind: ServerShareKind) -> None:
        """Count a link change within the caller's transaction; carries no identifiers."""
        await self._repo.add_share_event(kind)
