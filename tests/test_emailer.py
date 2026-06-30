"""Tests for the email digest: rendering, new/seen split, and the dry-run path."""

from datetime import datetime

from src import db, emailer
from src.aggregator import dedup_key
from src.config import get_config
from src.models import Event
from src.sources.util import LONDON_TZ


def _event(eid, artist, day, price=None, image=None):
    return Event(
        source="ticketmaster",
        source_event_id=eid,
        artist_name=artist,
        matched_artist=artist.lower(),
        venue="Village Underground",
        city="London",
        date=datetime(2026, 7, day, 20, tzinfo=LONDON_TZ),
        url=f"https://example/{eid}",
        price_from=price,
        links={"ticketmaster": f"https://example/{eid}"},
        image_url=image,
    )


def test_subject_counts_new():
    events = [_event("1", "Aphex Twin", 5), _event("2", "Bonobo", 6)]
    new_keys = {dedup_key(events[0])}
    subject = emailer.subject_line(events, new_keys)
    assert "2 London gigs" in subject
    assert "1 new" in subject


def test_render_marks_new_and_links_site():
    events = [
        _event("1", "Aphex Twin", 5, price=45, image="https://img/aphex.jpg"),
        _event("2", "Bonobo", 6),
    ]
    new_keys = {dedup_key(events[0])}
    subject, text, html = emailer.render_digest(events, new_keys)

    assert emailer.SITE_URL in text and emailer.SITE_URL in html
    assert "New this week" in text and "Still upcoming" in text
    assert "Aphex Twin" in html and "Bonobo" in html
    assert "from £45" in text
    assert ">NEW<" in html  # the new badge appears
    assert "https://img/aphex.jpg" in html  # artist photo
    assert "Resident Advisor" not in html  # only providers that are present
    assert "Ticketmaster" in html  # friendly provider label
    assert "s2/favicons" in html  # provider icon
    assert "—" not in html and "—" not in text  # no large dashes


def test_render_empty():
    subject, text, html = emailer.render_digest([], set())
    assert "0 London gigs" in subject
    assert emailer.SITE_URL in html


def test_get_sent_keys_and_mark_sent_roundtrip(tmp_path):
    path = str(tmp_path / "e.db")
    db.init_db(path)
    with db.connect(path) as conn:
        assert db.get_sent_keys(conn) == set()
        db.mark_sent(conn, {"a", "b"})
    with db.connect(path) as conn:
        db.mark_sent(conn, {"b", "c"})  # idempotent on "b"
    with db.connect(path) as conn:
        assert db.get_sent_keys(conn) == {"a", "b", "c"}


def test_run_digest_dry_run_does_not_send_or_mark(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "run.db"))
    get_config.cache_clear()
    config = get_config()
    db.init_db(config.db_path)

    # Seed one stored upcoming event.
    event = _event("1", "Aphex Twin", 5)
    with db.connect(config.db_path) as conn:
        db.upsert_event(conn, event, dedup_key(event))

    # A real send would raise (no transport configured); dry-run must not.
    sent_called = []
    monkeypatch.setattr(emailer, "send_email", lambda *a, **k: sent_called.append(1))

    subject = emailer.run_digest(config, dry_run=True)

    assert "1 London gigs" in subject
    assert sent_called == []  # nothing sent
    with db.connect(config.db_path) as conn:
        assert db.get_sent_keys(conn) == set()  # nothing marked
    assert "EMAIL DRY RUN" in capsys.readouterr().out
    get_config.cache_clear()


def test_run_digest_send_marks_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "send.db"))
    get_config.cache_clear()
    config = get_config()
    db.init_db(config.db_path)

    event = _event("1", "Aphex Twin", 5)
    with db.connect(config.db_path) as conn:
        db.upsert_event(conn, event, dedup_key(event))

    monkeypatch.setattr(emailer, "send_email", lambda *a, **k: None)
    emailer.run_digest(config, dry_run=False)

    with db.connect(config.db_path) as conn:
        assert dedup_key(event) in db.get_sent_keys(conn)
    get_config.cache_clear()
