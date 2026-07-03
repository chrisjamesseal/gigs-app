"""Network-free parser tests for the Ticketmaster and Bandsintown sources.

Each loads a canned fixture and asserts the parser produces correct ``Event``
objects, including London filtering and timezone handling.
"""

import json
from pathlib import Path

from src.sources import bandsintown, dice, ra, skiddle, ticketmaster
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
    # Village Underground (city=London) + EartH (Hackney, within 30km) - not Manchester.
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


# --- fragile scrapers: parser tests against the documented expected shape -----


def test_ra_parses_listings():
    events = ra.parse_events(_load("ra_sample.json"))
    assert len(events) == 2
    first = events[0]
    assert first.source == "ra"
    assert first.artist_name == "Aphex Twin"  # first artist in the lineup
    assert first.venue == "Fabric"
    assert first.url == "https://ra.co/events/1111111"  # contentUrl made absolute
    assert first.date.tzinfo is not None


def test_ra_degrades_on_unexpected_shape():
    # Schema drift must yield [] rather than raising.
    assert ra.parse_events({"data": {"somethingElse": {}}}) == []
    assert ra.parse_events({}) == []


def test_dice_keeps_only_london():
    events = dice.parse_events(_load("dice_sample.json"), queried_artist="Floating Points")
    ids = {e.source_event_id for e in events}
    assert ids == {"dice-1"}  # Manchester event excluded
    e = events[0]
    assert e.artist_name == "Floating Points"
    assert e.price_from == 22.0  # 2200 pence -> £22
    assert e.url == "https://dice.fm/event/dice-1"


def test_dice_degrades_on_unexpected_shape():
    assert dice.parse_events({"weird": True}, "Bonobo") == []
    assert dice.parse_events({}, "Bonobo") == []


def _load_html(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_dice_html_next_data():
    html = _load_html("dice_page.html")
    events = dice.parse_html(html, "Bicep")
    ids = {e.source_event_id for e in events}
    assert "dice-html-1" in ids
    assert "dice-html-2" in ids
    assert "dice-html-3" not in ids  # Manchester excluded
    bicep = next(e for e in events if e.source_event_id == "dice-html-1")
    assert bicep.artist_name == "Bicep"
    assert bicep.venue == "Printworks"
    assert bicep.price_from == 35.0  # 3500 pence -> £35
    assert bicep.url == "https://dice.fm/event/bicep-live"
    four_tet = next(e for e in events if e.source_event_id == "dice-html-2")
    assert four_tet.artist_name == "Four Tet"
    assert four_tet.url == "https://dice.fm/event/four-tet-dj-set"


def test_dice_html_jsonld_fallback():
    html = _load_html("dice_jsonld.html")
    events = dice.parse_html(html, "Ross From Friends")
    assert len(events) == 1
    e = events[0]
    assert e.artist_name == "Ross From Friends"
    assert e.venue == "Corsica Studios"
    assert e.price_from == 18.50
    assert e.url == "https://dice.fm/event/ross-from-friends"


def test_dice_html_degrades_on_empty():
    assert dice.parse_html("<html><body></body></html>", "Bonobo") == []
    assert dice.parse_html("", "Bonobo") == []
