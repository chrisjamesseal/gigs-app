"""Shared helpers for source modules: London timezone + geo distance."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")
# Charing Cross, the conventional centre of London.
CENTRAL_LONDON = (51.5074, -0.1278)


def to_london(dt: datetime) -> datetime:
    """Return a tz-aware datetime in Europe/London.

    Naive datetimes are assumed to already be London local (Bandsintown returns
    venue-local wall-clock times without an offset).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LONDON_TZ)
    return dt.astimezone(LONDON_TZ)


def parse_london_datetime(value: str) -> datetime:
    """Parse an ISO 8601 timestamp (with or without offset) into Europe/London."""
    # Accept a trailing 'Z' (UTC) which fromisoformat rejected before 3.11.
    cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return to_london(datetime.fromisoformat(cleaned))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    (lat1, lon1), (lat2, lon2) = a, b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))
