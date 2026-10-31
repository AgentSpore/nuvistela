from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import Forbidden, NotFound, Unauthorized

_STATUS: dict[type[Exception], int] = {Unauthorized: 401, Forbidden: 403, NotFound: 404}


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc)},
        status_code=next(code for t, code in _STATUS.items() if isinstance(exc, t)),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Map domain errors to HTTP statuses; the detail is the exception message."""
    for exc_type in _STATUS:
        app.add_exception_handler(exc_type, _domain_error)
