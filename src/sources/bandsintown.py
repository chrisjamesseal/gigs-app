"""Bandsintown source.

``GET /artists/{artist_name}/events?app_id={app_id}`` (host ``rest.bandsintown.com``).

No auth beyond the ``app_id`` query param. Bandsintown returns an artist's events
worldwide, so we keep only those whose venue city is London (case-insensitive) or
that sit within 30km of central London. Datetimes come back as venue-local
wall-clock strings with no offset, so we treat them as Europe/London.

Parsing lives in :func:`parse_events` for network-free testing.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import CENTRAL_LONDON, LONDON_TZ, haversine_km, parse_london_datetime

log = structlog.get_logger(__name__)

API_BASE = "https://rest.bandsintown.com/artists"
SOURCE = "bandsintown"
_TIMEOUT = httpx.Timeout(30.0)
_MAX_KM = 30.0


def _is_london(venue: dict) -> bool:
    if (venue.get("city") or "").strip().lower() == "london":
        return True
    try:
        lat = float(venue["latitude"])
        lon = float(venue["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    return haversine_km((lat, lon), CENTRAL_LONDON) <= _MAX_KM


def _ticket_url(raw: dict) -> str:
    for offer in raw.get("offers") or []:
        if (offer.get("type") or "").lower() == "tickets" and offer.get("url"):
            return offer["url"]
    return raw.get("url", "")


def parse_events(payload: list[dict], queried_artist: str) -> list[Event]:
    """Turn a Bandsintown artist-events response into London ``Event`` objects."""
    fetched_at = datetime.now(timezone.utc).astimezone(LONDON_TZ)
    events: list[Event] = []
    for raw in payload or []:
        venue = raw.get("venue") or {}
        if not _is_london(venue):
            continue
        if not raw.get("datetime"):
            continue
        # Prefer the explicit lineup headliner; fall back to the queried artist.
        lineup = raw.get("lineup") or []
        artist_name = lineup[0] if lineup else queried_artist
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=artist_name,
                venue=venue.get("name", ""),
                city=venue.get("city", "London"),
                date=parse_london_datetime(raw["datetime"]),
                url=_ticket_url(raw),
                price_from=None,  # Bandsintown doesn't expose price
                fetched_at=fetched_at,
            )
        )
    return events


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.bandsintown_app_id:
        log.warning("bandsintown.no_app_id")
        return []

    events: list[Event] = []
    with httpx.Client(timeout=_TIMEOUT) as client:
        for artist in artist_names:
            # Bandsintown wants the artist name path-encoded; '/' must become %252F.
            quoted = urllib.parse.quote(artist, safe="")
            url = f"{API_BASE}/{quoted}/events"
            resp = client.get(url, params={"app_id": config.bandsintown_app_id})
            if resp.status_code == 404:
                continue  # unknown artist — not an error
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                continue  # error objects come back as dicts
            events.extend(parse_events(payload, artist))
    return events
