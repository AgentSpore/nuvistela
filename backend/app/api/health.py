from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Report liveness and whether the database answers `SELECT 1`."""
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):  # driver, socket, connect timeout
        return JSONResponse({"status": "ok", "db": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})
