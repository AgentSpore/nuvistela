from typing import Literal, Self

from pydantic import BaseModel, Field

from app.repositories.share_repository import Share
from app.services.share_service import SharedLink, ShareStatus


class ShareCreated(BaseModel):
    token: str
    created: bool

    @classmethod
    def of(cls, link: SharedLink) -> Self:
        return cls(token=link.token, created=link.created)


class ShareState(BaseModel):
    """What the adult's preview needs: the vetted public title, the genre key, the active link."""

    title: str | None  # None: the card shows the genre words
    genre: Literal["fairy_tale", "space", "pirates", "custom"]
    token: str | None
    other_active: bool
    quests_done: int = Field(ge=0)  # the same counters the public card shows
    chapters: int = Field(ge=0)

    @classmethod
    def of(cls, status: ShareStatus) -> Self:
        counts = status.counts
        return cls.model_validate(
            {
                "title": status.title,
                "genre": status.genre,
                "token": status.token,
                "other_active": status.other_active,
                "quests_done": counts.quests_done,
                "chapters": counts.chapters,
            }
        )


class PublicShare(BaseModel):
    """Everything a stranger may see: nothing else is ever added here."""

    title: str | None  # None: the client shows the genre words
    genre: Literal["fairy_tale", "space", "pirates", "custom"]  # key; words are the client's
    cover_url: str
    quests_done: int = Field(ge=0)  # counts only: no quest or chapter text is ever shown
    chapters: int = Field(ge=0)

    @classmethod
    def of(cls, share: Share, token: str) -> Self:
        return cls.model_validate(
            {
                "title": share.title,
                "genre": share.genre,
                "cover_url": f"/api/v1/share/{token}/cover.webp",
                "quests_done": share.counts.quests_done,
                "chapters": share.counts.chapters,
            }
        )
