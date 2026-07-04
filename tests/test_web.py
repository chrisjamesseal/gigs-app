"""Smoke tests for the web app and the static-site render.

These don't hit the network: they exercise rendering against a temp SQLite DB.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src import db
from src.config import get_config
from src.models import Artist, Event
from src.sources.util import LONDON_TZ


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "web.db"))
    get_config.cache_clear()
    config = get_config()
    db.init_db(config.db_path)
    from src.web.app import app

    yield TestClient(app)
    get_config.cache_clear()


def test_index_renders_on_empty_db(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "London Gig Radar" in resp.text
    assert "No upcoming gigs yet" in resp.text


def test_api_events_empty(client):
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_static_render_includes_events(tmp_path):
    from src.aggregator import dedup_key
    from src.web.render import render_static_page

    event = Event(
        source="ticketmaster",
        source_event_id="1",
        artist_name="Aphex Twin",
        matched_artist="aphex twin",
        venue="Wembley Arena",
        city="London",
        date=datetime(2026, 7, 15, 20, tzinfo=LONDON_TZ),
        url="https://example/1",
        price_from=45.0,
        links={"ticketmaster": "https://example/1"},
    )
    html = render_static_page([event], last_run=None)
    assert "Aphex Twin" in html  # display uses source casing, not normalized
    assert "Wembley Arena" in html
    assert "Auto-updated weekly" in html
    assert 'action="/refresh"' not in html  # no live controls in the static build
    assert dedup_key(event)  # sanity: key builds without error


def _event(artist, venue, day, source="ticketmaster", url="https://ex/x"):
    return Event(
        source=source,
        source_event_id=f"{artist}-{venue}-{day}",
        artist_name=artist,
        matched_artist=artist.lower(),
        venue=venue,
        city="London",
        date=datetime(2026, 7, day, 20, tzinfo=LONDON_TZ),
        url=url,
        links={source: url},
    )


def test_cards_merge_same_artist_same_venue_multiple_days():
    from src.web.render import cards_from_events

    events = [
        _event("Bicep", "Printworks", 10, url="https://ex/fri"),
        _event("Bicep", "Printworks", 11, url="https://ex/sat"),
        _event("Four Tet", "Fabric", 12, url="https://ex/ft"),
    ]
    cards = cards_from_events(events)
    assert len(cards) == 2  # two Bicep nights merged into one card
    bicep = cards[0]
    assert bicep.artist_name == "Bicep"
    assert bicep.multi is True
    assert len(bicep.occurrences) == 2
    # occurrences stay in date order, each keeping its own link
    assert bicep.occurrences[0].links == {"ticketmaster": "https://ex/fri"}
    assert bicep.occurrences[1].links == {"ticketmaster": "https://ex/sat"}
    assert cards[1].multi is False


def test_multi_date_card_renders_each_night():
    from src.web.render import render_static_page

    events = [
        _event("Bicep", "Printworks", 10, url="https://ex/fri"),
        _event("Bicep", "Printworks", 11, url="https://ex/sat"),
    ]
    html = render_static_page(events, last_run=None)
    assert "2 dates" in html
    assert "https://ex/fri" in html
    assert "https://ex/sat" in html
    assert "Fri 10 Jul" in html
    assert "Sat 11 Jul" in html
