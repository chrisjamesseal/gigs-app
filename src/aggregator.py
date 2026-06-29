"""Fan out artist names across all enabled sources and collect events.

Each source is invoked behind :func:`src.sources.base.safe_fetch`, so one broken
source never blocks the digest. Dedup across sources lands in milestone 3; for now
this simply concatenates results. Returns the merged event list plus the set of
source names that failed (for the email's partial-coverage footer).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .config import Config
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
