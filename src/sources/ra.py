"""Resident Advisor source (scraper — FRAGILE, best-effort).

RA has no public API. This talks to the same private GraphQL endpoint
(``https://ra.co/graphql``) the website uses, which is reverse-engineered, sits in
a ToS grey area, and **will break without warning** when RA changes its schema.

Safeguards (per the spec):
- Kill switch: ``RA_ENABLED=false`` disables it instantly (checked in the
  aggregator, and again here defensively).
- Isolation: any failure is caught and returns ``[]`` — the rest of the app keeps
  working. The aggregator already wraps this in ``safe_fetch``; we also guard the
  parse so a schema drift degrades to "no events" rather than an exception.
- Politeness: a realistic User-Agent and a delay between requests.

Approach: query the London-area event listings (RA area id 13) over the lookahead
window, then let ``matcher`` keep only events by the user's artists. This avoids
having to resolve each artist to an RA id.

⚠️  REFRESHING THE QUERY: when this stops returning events, open an RA London
events page, inspect the Network tab for the ``graphql`` POST, and update
``GET_EVENT_LISTINGS`` / ``_variables`` below to match the current shape. See
REFRESHING_SCRAPERS.md.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from ..config import get_config
from ..models import Event
from .util import LONDON_TZ, parse_london_datetime

log = structlog.get_logger(__name__)

GRAPHQL_URL = "https://ra.co/graphql"
SOURCE = "ra"
RA_BASE = "https://ra.co"
LONDON_AREA_ID = 13
REQUEST_DELAY_S = 2.0
PAGE_SIZE = 50
MAX_PAGES = 5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Captured from the RA web app. Treat as version-specific and expect to refresh it.
GET_EVENT_LISTINGS = """
query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data {
      event {
        id
        title
        date
        startTime
        contentUrl
        venue { name }
        artists { name }
      }
    }
    totalResults
  }
}
"""


def _variables(page: int, lookahead_days: int) -> dict:
    today = datetime.now(LONDON_TZ).date()
    horizon = today + timedelta(days=lookahead_days)
    return {
        "page": page,
        "pageSize": PAGE_SIZE,
        "filters": {
            "areas": {"eq": LONDON_AREA_ID},
            "listingDate": {
                "gte": today.isoformat(),
                "lte": horizon.isoformat(),
            },
        },
    }


def _event_datetime(raw: dict) -> datetime | None:
    # Prefer a full startTime; fall back to the date at midnight London.
    for key in ("startTime", "date"):
        value = raw.get(key)
        if not value:
            continue
        try:
            return parse_london_datetime(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value[:10] + "T00:00:00").replace(
                    tzinfo=LONDON_TZ
                )
            except ValueError:
                continue
    return None


def parse_events(payload: dict) -> list[Event]:
    """Parse an RA ``eventListings`` GraphQL response into ``Event`` objects.

    Defensive against schema drift: anything unexpected yields fewer events, never
    an exception.
    """
    fetched_at = datetime.now(timezone.utc).astimezone(LONDON_TZ)
    listings = (
        ((payload or {}).get("data") or {}).get("eventListings") or {}
    ).get("data") or []

    events: list[Event] = []
    for listing in listings:
        raw = (listing or {}).get("event") or {}
        when = _event_datetime(raw)
        if when is None:
            continue
        artists = [a.get("name") for a in raw.get("artists") or [] if a.get("name")]
        artist_name = artists[0] if artists else raw.get("title", "")
        content_url = raw.get("contentUrl", "")
        url = RA_BASE + content_url if content_url.startswith("/") else content_url
        events.append(
            Event(
                source=SOURCE,
                source_event_id=str(raw.get("id", "")),
                artist_name=artist_name,
                venue=(raw.get("venue") or {}).get("name", ""),
                city="London",
                date=when,
                url=url,
                fetched_at=fetched_at,
            )
        )
    return events


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    config = get_config()
    if not config.ra_enabled:
        log.info("ra.disabled")
        return []

    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    events: list[Event] = []
    with httpx.Client(timeout=httpx.Timeout(30.0), headers=headers) as client:
        for page in range(1, MAX_PAGES + 1):
            body = {
                "query": GET_EVENT_LISTINGS,
                "variables": _variables(page, config.lookahead_days),
            }
            resp = client.post(GRAPHQL_URL, json=body)
            resp.raise_for_status()
            batch = parse_events(resp.json())
            events.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY_S)
    return events
