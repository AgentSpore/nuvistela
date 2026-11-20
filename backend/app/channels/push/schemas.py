from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from app.channels.push.endpoints import is_allowed_push_endpoint

ReminderKind = Literal["chapter_ready", "quest_waiting"]


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=64)


class SubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushKeys
    tz: str = Field(min_length=1, max_length=64)

    @field_validator("endpoint")
    @classmethod
    def _known_push_service(cls, endpoint: str) -> str:
        if not is_allowed_push_endpoint(endpoint):
            raise ValueError("endpoint must be an https URL of a known push service")
        return endpoint

    @field_validator("tz")
    @classmethod
    def _known_zone(cls, tz: str) -> str:
        try:
            ZoneInfo(tz)
        except (KeyError, ValueError, OSError) as exc:  # unknown key, malformed key, no tz data
            raise ValueError("unknown time zone") from exc
        return tz


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)


class OpenedRequest(BaseModel):
    kind: ReminderKind


class PublicKeyResponse(BaseModel):
    public_key: str
