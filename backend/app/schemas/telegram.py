from datetime import datetime

from pydantic import BaseModel


class LinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime
