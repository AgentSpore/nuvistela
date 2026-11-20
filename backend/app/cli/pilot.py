"""Anonymous pilot cohorts: `python -m app.cli.pilot --days 30`."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.repositories.pilot_repository import PilotRepository


def format_report(rows: list[dict], days: int) -> str:
    """Render aggregate stage counts with explicit cohort and conversion semantics."""
    lines = [
        f"Pilot cohorts: first server receipt in last {days} days; first-touch source/locale.",
        "Counts are distinct sessions, not people; stages need not occur in order.",
        "Stage counts/conversion include only sessions with landing_view; intent counts overlap.",
        "source locale sessions landing missing_landing demo_start demo_complete cta share lead "
        "lead_conversion solo family unordered",
    ]
    for row in rows:
        conversion = f"{row['lead'] / row['landing']:.1%}" if row["landing"] else "-"
        columns = [
            row[key]
            for key in (
                "source",
                "locale",
                "sessions",
                "landing",
                "missing_landing",
                "demo_start",
                "demo_complete",
                "cta",
                "share",
                "lead",
            )
        ]
        lines.append(
            " ".join(map(str, [*columns, conversion, row["solo"], row["family"], row["unordered"]]))
        )
    return "\n".join(lines)


def format_share_funnel(counts: dict[str, int], days: int) -> str:
    """Share-card funnel as plain counts; no per-family or per-link view."""
    lines = [f"Share funnel: events in last {days} days."]
    lines += [
        f"{label} {counts[key]} ({note})"
        for label, key, note in (
            ("created", "created", "links made"),
            ("viewed", "viewed", "sessions"),
            ("cta", "cta", "sessions"),
            ("new_leads", "leads", "lead with source=share, internal excluded"),
        )
    ]
    return "\n".join(lines)


async def _run(days: int, include_internal: bool) -> str:
    engine = create_async_engine(Settings().database_url)
    try:
        async with engine.connect() as conn:
            rows = await PilotRepository(conn).report(days, include_internal)
            funnel = await PilotRepository(conn).share_funnel(days)
            return f"{format_report(rows, days)}\n\n{format_share_funnel(funnel, days)}"
    finally:
        await engine.dispose()


def main() -> None:
    """Print the bounded-window pilot cohort report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--include-internal", action="store_true", help="count own checks too")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    print(asyncio.run(_run(args.days, args.include_internal)))


if __name__ == "__main__":
    main()
