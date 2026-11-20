from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.v1.deps import AdventureServiceDep, CurrentMember, get_conn
from app.repositories.adventure_repository import AdventureRepository
from app.schemas.adventure import (
    AdventureResponse,
    AdventureStarted,
    ChapterRef,
    DoneRequest,
    DoneResponse,
    QuestOut,
)
from app.schemas.world import WorldRequest

router = APIRouter(prefix="/api/v1")

IdempotencyKey = Annotated[str | None, Header(min_length=1, max_length=128)]


@router.post("/families/{family_id}/adventure")
async def start_adventure(
    family_id: UUID, body: WorldRequest, actor: CurrentMember, service: AdventureServiceDep
) -> AdventureStarted:
    view = await service.start(actor, family_id, body.to_form())
    quest = view.adventure.quest
    return AdventureStarted(
        world_status=view.world_status, quest=None if quest is None else QuestOut.of(quest)
    )


@router.get("/families/{family_id}/adventure")
async def get_adventure(
    family_id: UUID,
    actor: CurrentMember,
    service: AdventureServiceDep,
    conn: Annotated[AsyncConnection, Depends(get_conn, scope="function")],
) -> AdventureResponse:
    view = await service.get(actor, family_id)  # refuses another family before anything is written
    await AdventureRepository(conn).touch_poll(family_id)
    return AdventureResponse.of(view)


@router.post("/quests/{quest_id}/done")
async def mark_quest_done(
    quest_id: UUID,
    body: DoneRequest,
    actor: CurrentMember,
    service: AdventureServiceDep,
    idempotency_key: IdempotencyKey = None,
) -> DoneResponse:
    chapter = await service.done(actor, quest_id, body.note, idempotency_key)
    return DoneResponse(chapter=ChapterRef(id=chapter.id, status=chapter.status))


@router.post("/chapters/{chapter_id}/retry", status_code=202)
async def retry_chapter(
    chapter_id: UUID, actor: CurrentMember, service: AdventureServiceDep
) -> ChapterRef:
    chapter = await service.retry(actor, chapter_id)
    return ChapterRef(id=chapter.id, status=chapter.status)
