from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PilotLocale = Literal["ru", "en", "es", "zh-CN"]
PilotSource = Literal[
    "direct", "share", "community", "newsletter", "x", "telegram", "substack", "youtube"
]
PilotIntent = Literal["solo", "family"]
ClientKind = Literal[
    "landing_view",
    "demo_start",
    "demo_complete",
    "cta_click",
    "share_click",
    "share_viewed",
    "share_cta",
]
ServerShareKind = Literal["share_created", "share_revoked"]


class PilotAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    source: PilotSource
    intent: PilotIntent | None = None
    internal: bool = False


class PilotEventRequest(PilotAttribution):
    event_id: UUID
    kind: ClientKind
    locale: PilotLocale


class PilotEvent(PilotAttribution):
    event_id: UUID
    kind: ClientKind | Literal["lead_created"]
    locale: PilotLocale
