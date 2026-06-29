"""Fan out artist names across all enabled sources, collect and dedup events.

Each source is invoked behind :func:`src.sources.base.safe_fetch`, so one broken
source never blocks the run. Events for the same gig surfaced by multiple sources
are collapsed by :func:`dedup_events` on ``(matched_artist, date, venue)``, keeping
the most complete record and accumulating every source's URL in ``links``.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .config import Config
from .matcher import normalize_name
from .models import Event
from .sources import bandsintown, dice, ra, skiddle, ticketmaster
from .sources.base import safe_fetch

log = structlog.get_logger(__name__)


@dataclass
class AggregationResult:
    events: list[Event]
    failed_sources: list[str]


def _enabled_sources(config: Config):
    """Yield (name, fetch_fn) for every source switched on in config."""
    yield "ticketmaster", ticketmaster.fetch_events
    yield "bandsintown", bandsintown.fetch_events
    yield "skiddle", skiddle.fetch_events
    if config.ra_enabled:
        yield "ra", ra.fetch_events
    if config.dice_enabled:
        yield "dice", dice.fetch_events


def aggregate(
    artist_names: list[str], config: Config, location: str = "London"
) -> AggregationResult:
    """Query every enabled source and merge the results."""
    all_events: list[Event] = []
    failed: list[str] = []
    for name, fetch in _enabled_sources(config):
        events, ok = safe_fetch(name, fetch, artist_names, location)
        if not ok:
            failed.append(name)
        all_events.extend(events)
        log.debug("aggregate.source_done", source=name, added=len(events))
    return AggregationResult(events=all_events, failed_sources=failed)


def dedup_key(event: Event) -> str:
    """Stable key for the same gig across sources: artist + date + venue.

    Uses the matched artist when available (falling back to the raw name), the
    calendar date (ignoring start time, which sources report inconsistently), and
    the normalized venue.
    """
    artist = event.matched_artist or normalize_name(event.artist_name)
    return f"{artist}|{event.date.date().isoformat()}|{normalize_name(event.venue)}"


def _completeness(event: Event) -> int:
    """Rough score of how much detail a record carries, for picking a winner."""
    return sum(
        bool(x) for x in (event.venue, event.url, event.price_from, event.matched_artist)
    )


def dedup_events(events: list[Event]) -> list[Event]:
    """Collapse events that describe the same gig.

    Keeps the most complete record per :func:`dedup_key` and merges every source's
    URL into its ``links`` map (``{source: url}``), so the UI can show one "Tickets"
    link per source.
    """
    winners: dict[str, Event] = {}
    for event in events:
        key = dedup_key(event)
        current = winners.get(key)
        if current is None:
            # Seed links with this event's own source URL.
            if event.url:
                event.links.setdefault(event.source, event.url)
            winners[key] = event
            continue
        # Merge links, then keep whichever record is more complete.
        merged_links = {**current.links, **event.links}
        if event.url:
            merged_links.setdefault(event.source, event.url)
        winner = event if _completeness(event) > _completeness(current) else current
        winner.links = merged_links
        winners[key] = winner
    return list(winners.values())
