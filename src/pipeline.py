"""The end-to-end refresh pipeline, shared by the CLI and the web app.

    refresh artists (Spotify) -> aggregate sources -> match -> dedup -> store

Calling :func:`run_pipeline` repopulates the ``events`` table with the current set
of matched, deduped London gigs and records a run summary. The web UI then simply
reads ``events`` - it never hits the network on a page load.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from . import db, matcher, spotify_client
from .aggregator import aggregate, dedup_events, dedup_key
from .config import Config
from .models import Artist, Event

log = structlog.get_logger(__name__)


@dataclass
class PipelineResult:
    artists: int
    events_found: int
    matched: int
    stored: int
    failed_sources: list[str]


def _load_or_refresh_artists(config: Config, refresh: bool) -> list[Artist]:
    if refresh:
        artists = spotify_client.fetch_artists(config)
        with db.connect(config.db_path) as conn:
            db.upsert_artists(conn, artists)
        log.info("artists.cached", count=len(artists))
        return artists
    with db.connect(config.db_path) as conn:
        artists = db.get_artists(conn)
    log.info("artists.loaded_from_cache", count=len(artists))
    return artists


def run_pipeline(
    config: Config, *, refresh_artists: bool = True, location: str = "London"
) -> PipelineResult:
    """Run the full refresh and persist results. Returns a summary."""
    db.init_db(config.db_path)
    artists = _load_or_refresh_artists(config, refresh_artists)

    aggregated = aggregate([a.name for a in artists], config, location)

    with db.connect(config.db_path) as conn:
        matched = matcher.match_events(aggregated.events, artists, conn=conn)
        deduped = dedup_events(matched)
        db.clear_events(conn)
        for event in deduped:
            db.upsert_event(conn, event, dedup_key(event))
        db.record_run(
            conn,
            events_found=len(aggregated.events),
            matched=len(matched),
            failed_sources=aggregated.failed_sources,
        )

    result = PipelineResult(
        artists=len(artists),
        events_found=len(aggregated.events),
        matched=len(matched),
        stored=len(deduped),
        failed_sources=aggregated.failed_sources,
    )
    log.info("pipeline.complete", **result.__dict__)
    return result


def load_upcoming(config: Config) -> list[Event]:
    """Read stored upcoming events for display (no network)."""
    with db.connect(config.db_path) as conn:
        return db.get_upcoming_events(conn, config.lookahead_days)
