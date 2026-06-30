"""Skiddle source.

``GET /api/v1/events/search/?api_key={key}&keyword={artist}&eventcode=LIVE
   &latitude=51.5074&longitude=-0.1278&radius=15``

Skiddle covers both live gigs (``eventcode=LIVE``) and club/electronic nights
(``eventcode=CLUB``); we query both per artist and merge. Results are already
geo-constrained to ~15km of central London by the request, so no extra location
filtering is needed. Parsing is split into :func:`parse_events` for network-free
testing.

Skiddle's responses are loosely typed (prices as strings, occasionally missing
fields), so parsing is deliberately defensive.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import LONDON_TZ, parse_london_datetime

log = structlog.get_logger(__name__)

API_URL = "https://www.skiddle.com/api/v1/events/search/"
SOURCE = "skiddle"
EVENT_CODES = ("LIVE", "CLUB")
LATITUDE, LONGITUDE, RADIUS_KM = 51.5074, -0.1278, 15
_TIMEOUT = httpx.Timeout(30.0)
_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _price_from(raw: dict) -> float | None:
    """Pull a numeric 'from' price out of Skiddle's varied price fields."""
    for key in ("minPrice", "MinPrice", "entryprice", "EntryPrice"):
        value = raw.get(key)
        if value in (None, "", "0", 0):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        match = _PRICE_RE.search(str(value))
        if match:
            return float(match.group(1))
    return None


def _event_datetime(raw: dict) -> datetime | None:
    if raw.get("startdate"):  # ISO local, e.g. "2026-07-01T19:00:00"
        try:
            return parse_london_datetime(raw["startdate"])
        except ValueError:
            pass
    if raw.get("date"):  # date only "2026-07-01"
        try:
            return datetime.fromisoformat(f"{raw['date']}T00:00:00").replace(
                tzinfo=LONDON_TZ
            )
        except ValueError:
            return None
    return None


def parse_events(payload: dict, queried_artist: str) -> list[Event]:
    """Turn a Skiddle search response into ``Event`` objects.

    ``queried_artist`` is used as the event's artist name: Skiddle has no clean
    line-up field, and the result set is the response to a keyword search for that
    artist, so the matcher confirms it against the user's artists.
    """
    if payload.get("error"):  # nonzero error code -> treat as no results
        log.warning("skiddle.api_error", error=payload.get("error"))
        return []

    fetched_at = datetime.now(timezone.utc).astimezone(LONDON_TZ)
    events: list[Event] = []
    for raw in payload.get("results") or []:
        when = _event_datetime(raw)
        if when is None:
            continue
        venue = raw.get("venue") or {}
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=queried_artist,
                venue=venue.get("name", ""),
                city=venue.get("town", "London") or "London",
                date=when,
                url=raw.get("link", ""),
                price_from=_price_from(raw),
                fetched_at=fetched_at,
            )
        )
    return events


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.skiddle_api_key:
        log.warning("skiddle.no_api_key")
        return []

    base_params = {
        "api_key": config.skiddle_api_key,
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "radius": RADIUS_KM,
    }
    events: list[Event] = []
    with httpx.Client(timeout=_TIMEOUT) as client:
        for artist in artist_names:
            for code in EVENT_CODES:
                params = {**base_params, "keyword": artist, "eventcode": code}
                resp = client.get(API_URL, params=params)
                resp.raise_for_status()
                events.extend(parse_events(resp.json(), artist))
    return events
