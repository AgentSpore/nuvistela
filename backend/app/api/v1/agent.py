from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError

from app.agent.models import AgentEvent
from app.api.v1.deps import AgentGatewayDep, CurrentMember
from app.schemas.agent import AgentMessageRequest, AgentMessageResponse

router = APIRouter(prefix="/api/v1")


@router.post("/agent/messages")
async def post_message(
    body: AgentMessageRequest, member: CurrentMember, gateway: AgentGatewayDep, request: Request
) -> AgentMessageResponse:
    # Body size before parsing is not limited here: K5 sets Caddy `request_body max_size`.
    limit = request.app.state.settings.agent_max_text_chars
    if len(body.text) > limit:
        raise RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "text"),
                    "msg": f"String should have at most {limit} characters",
                    "ctx": {"max_length": limit},
                }
            ]
        )
    event = AgentEvent(
        family_id=str(member.family_id),
        member_id=str(member.id),
        channel="web",
        kind="message",
        text=body.text,
    )
    return AgentMessageResponse(reply=(await gateway.handle(event)).text)
