"""Dice source (scraper — FRAGILE, best-effort).

Dice has no public API. This talks to the private API (``https://api.dice.fm/``)
its web/app clients use — reverse-engineered, ToS grey area, and **liable to break
without warning**.

Safeguards mirror the RA source:
- Kill switch ``DICE_ENABLED=false`` (checked in the aggregator and here).
- Isolation: failures degrade to ``[]`` (the aggregator wraps this in
  ``safe_fetch``; parsing is also defensive).
- Politeness: realistic User-Agent and an inter-request delay.

Approach: per-artist keyword search, keeping results whose venue city is London.

⚠️  REFRESHING THE QUERY: when this stops returning events, open dice.fm, inspect
the Network tab for the search/events request to ``api.dice.fm``, and update the
endpoint/params/parse below. See REFRESHING_SCRAPERS.md.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import parse_london_datetime

log = structlog.get_logger(__name__)

SEARCH_URL = "https://api.dice.fm/v2/events"
SOURCE = "dice"
REQUEST_DELAY_S = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _venue_city(raw: dict) -> tuple[str, str]:
    venue = raw.get("venue") or {}
    name = venue.get("name", "")
    city = venue.get("city")
    if isinstance(city, dict):  # sometimes nested {"name": "London"}
        city = city.get("name", "")
    return name, city or ""


def _price_from(raw: dict) -> float | None:
    # Dice prices appear in minor units (pence) under varying keys.
    for key in ("price", "min_price", "ticket_price"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return round(value / 100, 2) if value >= 1000 else float(value)
    return None


def _event_datetime(raw: dict) -> datetime | None:
    for key in ("date", "started_at", "start_date"):
        value = raw.get(key)
        if value:
            try:
                return parse_london_datetime(value)
            except ValueError:
                continue
    return None


def parse_events(payload: dict, queried_artist: str) -> list[Event]:
    """Parse a Dice events search response, keeping only London events.

    Defensive against schema drift: unexpected shapes yield fewer events, never an
    exception.
    """
    fetched_at = datetime.now(timezone.utc)
    results = (payload or {}).get("data") or (payload or {}).get("events") or []

    events: list[Event] = []
    for raw in results:
        venue, city = _venue_city(raw)
        if city.strip().lower() != "london":
            continue
        when = _event_datetime(raw)
        if when is None:
            continue
        lineup = raw.get("summary_lineup") or raw.get("artists") or []
        if isinstance(lineup, list) and lineup:
            first = lineup[0]
            artist_name = first.get("name") if isinstance(first, dict) else str(first)
        else:
            artist_name = queried_artist
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=artist_name or queried_artist,
                venue=venue,
                city=city or "London",
                date=when,
                url=raw.get("permalink") or raw.get("url", ""),
                price_from=_price_from(raw),
                fetched_at=fetched_at,
            )
        )
    return events


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.dice_enabled:
        log.info("dice.disabled")
        return []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    events: list[Event] = []
    with httpx.Client(timeout=httpx.Timeout(30.0), headers=headers) as client:
        for artist in artist_names:
            params = {"q": artist, "city": location}
            resp = client.get(SEARCH_URL, params=params)
            resp.raise_for_status()
            events.extend(parse_events(resp.json(), artist))
            time.sleep(REQUEST_DELAY_S)
    return events
