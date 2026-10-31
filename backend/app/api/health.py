import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()

# Docker HEALTHCHECK allows 2s; stay below it even if the DB host drops packets.
DB_CHECK_TIMEOUT_S = 1.5


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Report liveness and whether the database answers `SELECT 1`."""
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_S), request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):  # driver, socket, connect timeout
        return JSONResponse({"status": "degraded", "db": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})
