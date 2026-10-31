from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.errors import AgentBudgetExceededError, AgentUnavailableError
from app.domain.errors import Forbidden, NotFound, Unauthorized

_STATUS: dict[type[Exception], int] = {Unauthorized: 401, Forbidden: 403, NotFound: 404}
# Agent failures carry provider text; the client gets a fixed message instead.
_AGENT: dict[type[Exception], tuple[int, str]] = {
    AgentBudgetExceededError: (429, "the game master has reached today's limit"),
    AgentUnavailableError: (503, "the game master is unavailable, try again later"),
}


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc)},
        status_code=next(code for t, code in _STATUS.items() if isinstance(exc, t)),
    )


async def _agent_error(_: Request, exc: Exception) -> JSONResponse:
    status, detail = next(v for t, v in _AGENT.items() if isinstance(exc, t))
    return JSONResponse({"detail": detail}, status_code=status)


def register_error_handlers(app: FastAPI) -> None:
    """Map domain and agent errors to HTTP statuses."""
    for exc_type in _STATUS:
        app.add_exception_handler(exc_type, _domain_error)
    for exc_type in _AGENT:
        app.add_exception_handler(exc_type, _agent_error)
