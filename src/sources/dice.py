"""Dice source (scraper - FRAGILE, best-effort).

⚠️  DISABLED BY DEFAULT (``DICE_ENABLED=false``). dice.fm blocks datacenter IPs:
every request from GitHub Actions comes back ``403 Forbidden``, so this returns
nothing and only slows the build. Resident Advisor covers the same electronic/club
scene. The scraper is kept here in case Dice's blocking eases or the job runs from
a residential IP; flip ``DICE_ENABLED=true`` to try it.

Dice has no public API. This scrapes event data from the dice.fm website by
fetching artist search pages and parsing the embedded JSON (Next.js
``__NEXT_DATA__`` or JSON-LD structured data).

Safeguards mirror the RA source:
- Kill switch ``DICE_ENABLED=false`` (checked in the aggregator and here).
- Isolation: failures degrade to ``[]`` (the aggregator wraps this in
  ``safe_fetch``; parsing is also defensive).
- Politeness: realistic User-Agent and an inter-request delay.

Approach: per-artist search on dice.fm, keeping results whose venue city is
London.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import parse_london_datetime

log = structlog.get_logger(__name__)

SEARCH_URL = "https://dice.fm/search"
DICE_BASE = "https://dice.fm"
SOURCE = "dice"
REQUEST_DELAY_S = 1.5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>', re.DOTALL
)
_JSONLD_RE = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)


def _is_london(venue_obj: dict | str | None) -> bool:
    if not venue_obj:
        return False
    if isinstance(venue_obj, str):
        return "london" in venue_obj.lower()
    city = venue_obj.get("city") or venue_obj.get("addressLocality") or ""
    if isinstance(city, dict):
        city = city.get("name", "")
    address = venue_obj.get("address") or {}
    if isinstance(address, dict):
        locality = address.get("addressLocality", "")
        region = address.get("addressRegion", "")
        full = f"{locality} {region}"
    else:
        full = str(address)
    return "london" in city.lower() or "london" in full.lower()


def _venue_name(venue_obj: dict | str | None) -> str:
    if not venue_obj:
        return ""
    if isinstance(venue_obj, str):
        return venue_obj
    return venue_obj.get("name", "")


def _venue_city(venue_obj: dict | str | None) -> str:
    if not venue_obj:
        return ""
    if isinstance(venue_obj, str):
        return ""
    city = venue_obj.get("city") or ""
    if isinstance(city, dict):
        city = city.get("name", "")
    if not city:
        addr = venue_obj.get("address") or {}
        if isinstance(addr, dict):
            city = addr.get("addressLocality", "")
    return city or "London"


def _price_from(raw: dict) -> float | None:
    for key in ("price", "min_price", "ticket_price", "lowPrice"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return round(value / 100, 2) if value >= 1000 else float(value)
    offers = raw.get("offers")
    if isinstance(offers, dict):
        lp = offers.get("lowPrice") or offers.get("price")
        if isinstance(lp, (int, float)) and lp > 0:
            return float(lp)
        if isinstance(lp, str):
            try:
                return float(lp)
            except ValueError:
                pass
    if isinstance(offers, list):
        prices = []
        for o in offers:
            p = o.get("price")
            if isinstance(p, (int, float)) and p > 0:
                prices.append(float(p))
            elif isinstance(p, str):
                try:
                    prices.append(float(p))
                except ValueError:
                    pass
        if prices:
            return min(prices)
    return None


def _event_datetime(raw: dict) -> datetime | None:
    for key in ("date", "started_at", "start_date", "startDate", "doorTime"):
        value = raw.get(key)
        if value and isinstance(value, str):
            try:
                return parse_london_datetime(value)
            except ValueError:
                continue
    return None


def _event_url(raw: dict) -> str:
    for key in ("permalink", "url", "contentUrl"):
        value = raw.get(key)
        if value and isinstance(value, str):
            if value.startswith("/"):
                return DICE_BASE + value
            if value.startswith("http"):
                return value
    return ""


def _extract_artist(raw: dict, fallback: str) -> str:
    lineup = raw.get("summary_lineup") or raw.get("artists") or raw.get("performer")
    if isinstance(lineup, list) and lineup:
        first = lineup[0]
        if isinstance(first, dict):
            return first.get("name", fallback)
        if isinstance(first, str):
            return first
    name = raw.get("name") or raw.get("title") or ""
    if isinstance(name, str) and name:
        return name
    return fallback


def _parse_next_data(html: str, queried_artist: str) -> list[Event]:
    """Extract events from Next.js __NEXT_DATA__ embedded JSON."""
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    events: list[Event] = []
    fetched_at = datetime.now(timezone.utc)

    props = (data.get("props") or {}).get("pageProps") or {}

    raw_events = []
    for key in ("events", "results", "data", "searchResults", "items"):
        candidate = props.get(key)
        if isinstance(candidate, list) and candidate:
            raw_events = candidate
            break
    if not raw_events and isinstance(props, dict):
        for v in props.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and any(
                k in v[0] for k in ("venue", "date", "startDate", "started_at")
            ):
                raw_events = v
                break

    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        venue_obj = raw.get("venue") or raw.get("location")
        if not _is_london(venue_obj):
            continue
        when = _event_datetime(raw)
        if when is None:
            continue
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=_extract_artist(raw, queried_artist),
                venue=_venue_name(venue_obj),
                city=_venue_city(venue_obj),
                date=when,
                url=_event_url(raw),
                price_from=_price_from(raw),
                fetched_at=fetched_at,
            )
        )
    return events


def _parse_jsonld(html: str, queried_artist: str) -> list[Event]:
    """Extract events from JSON-LD structured data."""
    events: list[Event] = []
    fetched_at = datetime.now(timezone.utc)

    for match in _JSONLD_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if data.get("@type") not in ("Event", "MusicEvent"):
            continue
        venue_obj = data.get("location") or {}
        if not _is_london(venue_obj):
            continue
        when = _event_datetime(data)
        if when is None:
            continue
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(data.get("identifier", data.get("url", ""))),
                artist_name=_extract_artist(data, queried_artist),
                venue=_venue_name(venue_obj),
                city=_venue_city(venue_obj),
                date=when,
                url=_event_url(data),
                price_from=_price_from(data),
                fetched_at=fetched_at,
            )
        )
    return events


def parse_events(payload: dict, queried_artist: str) -> list[Event]:
    """Parse a Dice API-style response, keeping only London events.

    Retained for backward compatibility and testing with the old JSON shape.
    """
    fetched_at = datetime.now(timezone.utc)
    results = (payload or {}).get("data") or (payload or {}).get("events") or []

    events: list[Event] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        venue_obj = raw.get("venue") or {}
        venue_name = _venue_name(venue_obj)
        city = _venue_city(venue_obj)
        if city.strip().lower() != "london":
            continue
        when = _event_datetime(raw)
        if when is None:
            continue
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=_extract_artist(raw, queried_artist),
                venue=venue_name,
                city=city or "London",
                date=when,
                url=_event_url(raw),
                price_from=_price_from(raw),
                fetched_at=fetched_at,
            )
        )
    return events


def parse_html(html: str, queried_artist: str) -> list[Event]:
    """Parse a Dice webpage for event data.

    Tries __NEXT_DATA__ first (most reliable), then JSON-LD fallback.
    """
    events = _parse_next_data(html, queried_artist)
    if not events:
        events = _parse_jsonld(html, queried_artist)
    return events


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.dice_enabled:
        log.info("dice.disabled")
        return []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    events: list[Event] = []
    diagnosed = False
    with httpx.Client(
        timeout=httpx.Timeout(30.0), headers=headers, follow_redirects=True
    ) as client:
        for artist in artist_names:
            try:
                resp = client.get(
                    SEARCH_URL, params={"query": artist, "type": "events"}
                )
                resp.raise_for_status()
                body = resp.text
                if not diagnosed:
                    # One-time visibility into what the runner actually receives, so
                    # a zero-result Dice run can be diagnosed from the CI logs without
                    # needing to reproduce the (egress-restricted) request locally.
                    log.info(
                        "dice.first_response",
                        artist=artist,
                        status=resp.status_code,
                        length=len(body),
                        has_next_data="__NEXT_DATA__" in body,
                        has_jsonld="application/ld+json" in body,
                        final_url=str(resp.url),
                    )
                    diagnosed = True
                batch = parse_html(body, artist)
                events.extend(batch)
                log.debug("dice.artist_done", artist=artist, events=len(batch))
            except Exception as exc:  # noqa: BLE001
                log.warning("dice.artist_failed", artist=artist, error=str(exc))
            time.sleep(REQUEST_DELAY_S)
    log.info("dice.done", artists=len(artist_names), events=len(events))
    return events
