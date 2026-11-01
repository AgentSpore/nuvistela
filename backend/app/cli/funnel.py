"""Funnel report: `python -m app.cli.funnel --days 30`."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.domain.funnel import FunnelStep
from app.repositories.funnel_repository import FunnelRepository


def format_report(steps: list[FunnelStep], days: int) -> str:
    lines = [f"Funnel, last {days} days", f"{'step':<20}{'count':>8}{'conversion':>12}"]
    for step in steps:
        conv = "-" if step.conversion is None else f"{step.conversion:.1%}"
        lines.append(f"{step.kind.value:<20}{step.count:>8}{conv:>12}")
    lines.append("return_d1/return_d7: families created in the window with a returning member")
    return "\n".join(lines)


async def _run(days: int) -> str:
    engine = create_async_engine(Settings().database_url)
    try:
        async with engine.connect() as conn:
            return format_report(await FunnelRepository(conn).report(days), days)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    print(asyncio.run(_run(parser.parse_args().days)))


if __name__ == "__main__":
    main()
