"""Tests for cross-source dedup logic."""

from datetime import datetime

from src.aggregator import dedup_events, dedup_key
from src.models import Event
from src.sources.util import LONDON_TZ


def _event(source, eid, artist, venue, day, url, price=None, matched=None):
    return Event(
        source=source,
        source_event_id=eid,
        artist_name=artist,
        matched_artist=matched,
        venue=venue,
        city="London",
        date=datetime(2026, 7, day, 20, tzinfo=LONDON_TZ),
        url=url,
        price_from=price,
    )


def test_dedup_key_ignores_time_and_normalizes_venue():
    a = _event("ticketmaster", "1", "Bonobo", "The O2 Arena", 5, "u1", matched="bonobo")
    b = _event("dice", "2", "Bonobo", "the o2 arena!", 5, "u2", matched="bonobo")
    assert dedup_key(a) == dedup_key(b)


def test_dedup_merges_links_from_both_sources():
    a = _event("ticketmaster", "1", "Bonobo", "O2", 5, "tm-url", matched="bonobo")
    b = _event("dice", "2", "Bonobo", "O2", 5, "dice-url", matched="bonobo")
    merged = dedup_events([a, b])
    assert len(merged) == 1
    assert merged[0].links == {"ticketmaster": "tm-url", "dice": "dice-url"}


def test_dedup_keeps_most_complete_record():
    sparse = _event("dice", "2", "Bonobo", "O2", 5, "dice-url", matched="bonobo")
    rich = _event(
        "ticketmaster", "1", "Bonobo", "O2", 5, "tm-url", price=40.0, matched="bonobo"
    )
    merged = dedup_events([sparse, rich])
    assert len(merged) == 1
    assert merged[0].price_from == 40.0  # the richer record won
    # ...but it still carries both source links.
    assert set(merged[0].links) == {"ticketmaster", "dice"}


def test_dedup_keeps_distinct_gigs_separate():
    a = _event("ticketmaster", "1", "Bonobo", "O2", 5, "u1", matched="bonobo")
    b = _event("ticketmaster", "2", "Bonobo", "Brixton", 6, "u2", matched="bonobo")
    assert len(dedup_events([a, b])) == 2
