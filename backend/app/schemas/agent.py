from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    """Upper length comes from settings (`agent_max_text_chars`), enforced in the route."""

    text: str = Field(min_length=1)


class AgentMessageResponse(BaseModel):
    reply: str
