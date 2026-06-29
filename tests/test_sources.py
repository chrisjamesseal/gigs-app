"""Network-free parser tests for the Ticketmaster and Bandsintown sources.

Each loads a canned fixture and asserts the parser produces correct ``Event``
objects, including London filtering and timezone handling.
"""

import json
from pathlib import Path

from src.sources import bandsintown, skiddle, ticketmaster
from src.sources.util import LONDON_TZ

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


def test_ticketmaster_parses_events():
    events = ticketmaster.parse_events(_load("ticketmaster_sample.json"))
    assert len(events) == 2

    aphex = next(e for e in events if e.source_event_id == "G5vYZ9abc123")
    assert aphex.source == "ticketmaster"
    assert aphex.artist_name == "Aphex Twin"
    assert aphex.venue == "Wembley Arena"
    assert aphex.city == "London"
    assert aphex.price_from == 45.0
    assert aphex.date.tzinfo is not None
    # 19:00 UTC -> 20:00 Europe/London (BST) in July.
    assert aphex.date.astimezone(LONDON_TZ).hour == 20


def test_ticketmaster_handles_date_only_event():
    events = ticketmaster.parse_events(_load("ticketmaster_sample.json"))
    bonobo = next(e for e in events if e.source_event_id == "G5vYZ9def456")
    assert bonobo.artist_name == "Bonobo"
    assert bonobo.price_from is None
    assert bonobo.date.tzinfo is not None


def test_bandsintown_keeps_only_london_events():
    events = bandsintown.parse_events(
        _load("bandsintown_sample.json"), queried_artist="Floating Points"
    )
    # Village Underground (city=London) + EartH (Hackney, within 30km) — not Manchester.
    ids = {e.source_event_id for e in events}
    assert ids == {"1001", "1003"}


def test_bandsintown_prefers_ticket_offer_url():
    events = bandsintown.parse_events(
        _load("bandsintown_sample.json"), queried_artist="Floating Points"
    )
    village = next(e for e in events if e.source_event_id == "1001")
    assert village.url == "https://tickets.example/1001"
    assert village.artist_name == "Floating Points"
    assert village.venue == "Village Underground"
    assert village.date.tzinfo is not None


def test_skiddle_parses_and_skips_dateless():
    events = skiddle.parse_events(
        _load("skiddle_sample.json"), queried_artist="Bonobo"
    )
    # The third result has no date and is dropped.
    ids = {e.source_event_id for e in events}
    assert ids == {"40123456", "40123457"}
    for e in events:
        assert e.source == "skiddle"
        assert e.artist_name == "Bonobo"  # the queried keyword
        assert e.date.tzinfo is not None


def test_skiddle_parses_varied_price_fields():
    events = skiddle.parse_events(
        _load("skiddle_sample.json"), queried_artist="Bonobo"
    )
    by_id = {e.source_event_id: e for e in events}
    assert by_id["40123456"].price_from == 25.50  # numeric string
    assert by_id["40123457"].price_from == 18.0  # "£18"


def test_skiddle_handles_api_error():
    assert skiddle.parse_events({"error": 3, "errormessage": "bad"}, "Bonobo") == []
