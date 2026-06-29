"""Ticketmaster Discovery API source.

``GET /discovery/v2/events.json?city=London&countryCode=GB&keyword={artist}&size=50``

A free API key (``TICKETMASTER_API_KEY``) with a generous 5000/day limit. We query
one artist at a time (the ``keyword`` filter) and back off on HTTP 429. Parsing is
split out into :func:`parse_events` so it can be tested against a fixture without
touching the network.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import LONDON_TZ, parse_london_datetime

log = structlog.get_logger(__name__)

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
SOURCE = "ticketmaster"
_TIMEOUT = httpx.Timeout(30.0)
_MAX_RETRIES = 3


def _artist_name(raw: dict) -> str:
    """Best available performer name: first attraction, else the event name."""
    attractions = (raw.get("_embedded") or {}).get("attractions") or []
    if attractions and attractions[0].get("name"):
        return attractions[0]["name"]
    return raw.get("name", "")


def _venue_and_city(raw: dict) -> tuple[str, str]:
    venues = (raw.get("_embedded") or {}).get("venues") or []
    if not venues:
        return "", ""
    v = venues[0]
    return v.get("name", ""), (v.get("city") or {}).get("name", "")


def _event_datetime(raw: dict) -> datetime | None:
    dates = (raw.get("dates") or {}).get("start") or {}
    if dates.get("dateTime"):  # UTC instant, e.g. "2026-07-01T19:00:00Z"
        return parse_london_datetime(dates["dateTime"])
    if dates.get("localDate"):  # date only; pin to local time if given, else 00:00
        date_part = dates["localDate"]
        time_part = dates.get("localTime", "00:00:00")
        naive = datetime.fromisoformat(f"{date_part}T{time_part}")
        return naive.replace(tzinfo=LONDON_TZ)
    return None


def _price_from(raw: dict) -> float | None:
    ranges = raw.get("priceRanges") or []
    mins = [r["min"] for r in ranges if r.get("min") is not None]
    return min(mins) if mins else None


def parse_events(payload: dict) -> list[Event]:
    """Turn a Discovery API response into ``Event`` objects."""
    fetched_at = datetime.now(timezone.utc).astimezone(LONDON_TZ)
    raw_events = (payload.get("_embedded") or {}).get("events") or []
    events: list[Event] = []
    for raw in raw_events:
        when = _event_datetime(raw)
        if when is None:
            continue
        venue, city = _venue_and_city(raw)
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=_artist_name(raw),
                venue=venue,
                city=city,
                date=when,
                url=raw.get("url", ""),
                price_from=_price_from(raw),
                fetched_at=fetched_at,
            )
        )
    return events


def _get_with_backoff(client: httpx.Client, params: dict) -> httpx.Response | None:
    """GET with exponential backoff on 429; return None if retries are exhausted."""
    delay = 2.0
    for attempt in range(_MAX_RETRIES):
        resp = client.get(API_URL, params=params)
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", delay))
            log.warning("ticketmaster.rate_limited", attempt=attempt + 1, wait=wait)
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp
    return None


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.ticketmaster_api_key:
        log.warning("ticketmaster.no_api_key")
        return []

    base_params = {
        "apikey": config.ticketmaster_api_key,
        "city": location,
        "countryCode": "GB",
        "size": 50,
    }
    events: list[Event] = []
    with httpx.Client(timeout=_TIMEOUT) as client:
        for artist in artist_names:
            params = {**base_params, "keyword": artist}
            resp = _get_with_backoff(client, params)
            if resp is None:
                continue
            events.extend(parse_events(resp.json()))
    return events
