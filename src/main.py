"""CLI entrypoint for the London Gig Radar pipeline.

Run as ``python -m src.main``. It runs the full refresh — pull Spotify artists,
query gig sources, match, dedup, and store events in SQLite — then prints the
stored upcoming gigs. The same pipeline backs the web app (``python -m src.web``);
this is the headless way to populate the database (e.g. from cron).

Flags:
    --refresh-artists / --no-refresh-artists
                Force or skip the Spotify artist refresh (default: on).
    --email     After refreshing, send the weekly email digest.
    --dry-run   With --email, render and log the digest instead of sending it.
"""

from __future__ import annotations

import argparse
import sys

import structlog

from .config import get_config
from .logging_config import configure_logging
from .models import Event
from .pipeline import load_upcoming, run_pipeline

log = structlog.get_logger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gig-radar", description=__doc__)
    parser.add_argument(
        "--refresh-artists",
        dest="refresh_artists",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh the cached Spotify artist list (default: on).",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Send the weekly email digest after refreshing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --email, render and log the digest instead of sending.",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    config = get_config()

    result = run_pipeline(config, refresh_artists=args.refresh_artists)
    log.info("artists.summary", total=result.artists)

    _print_events(load_upcoming(config), result.failed_sources)

    if args.email:
        from . import emailer

        subject = emailer.run_digest(config, dry_run=args.dry_run)
        log.info("email.done", subject=subject, dry_run=args.dry_run)
    return 0


def _print_events(events: list[Event], failed_sources: list[str]) -> None:
    """Print stored upcoming events to the console, soonest first."""
    print(f"\nUpcoming London gigs by your artists ({len(events)}):")
    if not events:
        print("  (none yet — add API keys and refresh, or none were found)")
    for event in events:
        when = event.date.strftime("%a %d %b %Y %H:%M")
        price = f" from £{event.price_from:.0f}" if event.price_from else ""
        sources = ", ".join(event.links.keys()) or event.source
        print(
            f"  - {when}  {event.artist_name} @ {event.venue}"
            f"  [{sources}]{price}"
        )
        print(f"      {event.url}")
    if failed_sources:
        print(f"\n⚠️  Sources unavailable this run: {', '.join(failed_sources)}")


def main() -> None:
    try:
        sys.exit(run())
    except RuntimeError as exc:
        # Expected, actionable errors (e.g. missing config) — no traceback noise.
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
