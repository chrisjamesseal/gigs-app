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
