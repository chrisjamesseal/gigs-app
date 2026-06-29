"""Entrypoint for the London Gig Radar pipeline.

Run as ``python -m src.main``. Milestone 1 wires up the front of the pipeline:
initialize the database, pull the user's Spotify artists (followed + liked),
cache them, and print them. Later milestones extend :func:`run` to query gig
sources, match, dedup, store, and email.

Flags:
    --dry-run   Run the full pipeline but never send email (logs instead).
    --refresh-artists / --no-refresh-artists
                Force or skip the weekly Spotify artist refresh.
"""

from __future__ import annotations

import argparse
import sys

import structlog

from . import db, matcher, spotify_client
from .aggregator import aggregate
from .config import get_config
from .logging_config import configure_logging

log = structlog.get_logger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gig-radar", description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline but log the email instead of sending it.",
    )
    parser.add_argument(
        "--refresh-artists",
        dest="refresh_artists",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh the cached Spotify artist list (default: on).",
    )
    return parser.parse_args(argv)


def refresh_artists(config) -> list:
    """Fetch artists from Spotify and cache them in SQLite. Returns the list."""
    artists = spotify_client.fetch_artists(config)
    with db.connect(config.db_path) as conn:
        written = db.upsert_artists(conn, artists)
    log.info("artists.cached", count=written)
    return artists


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    config = get_config()

    db.init_db(config.db_path)
    log.info("db.ready", path=config.db_path)

    if args.refresh_artists:
        artists = refresh_artists(config)
    else:
        with db.connect(config.db_path) as conn:
            artists = db.get_artists(conn)
        log.info("artists.loaded_from_cache", count=len(artists))

    followed = sum(1 for a in artists if a.source == "followed")
    liked = len(artists) - followed
    log.info("artists.summary", total=len(artists), followed=followed, liked=liked)

    # Milestone 2: query enabled sources, match events back to the user's artists,
    # and print the matches to the console.
    result = aggregate([a.name for a in artists], config)
    with db.connect(config.db_path) as conn:
        matched = matcher.match_events(result.events, artists, conn=conn)

    _print_events(matched, result.failed_sources)

    # Milestones 3+ continue from here: dedup -> store -> email.
    log.info(
        "run.complete",
        dry_run=args.dry_run,
        artists=len(artists),
        events_found=len(result.events),
        matched=len(matched),
        failed_sources=result.failed_sources,
    )
    return 0


def _print_events(events: list, failed_sources: list[str]) -> None:
    """Print matched events to the console, grouped by date (milestone 2 output)."""
    print(f"\nMatched gigs in London ({len(events)}):")
    if not events:
        print("  (none — no matching upcoming events found)")
    for event in sorted(events, key=lambda e: e.date):
        when = event.date.strftime("%a %d %b %Y %H:%M")
        price = f" from £{event.price_from:.0f}" if event.price_from else ""
        print(
            f"  - {when}  {event.artist_name} @ {event.venue}"
            f"  [{event.source}]{price}"
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
