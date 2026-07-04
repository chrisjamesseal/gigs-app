"""Tests for artist-name normalization.

The fuzzy-matching tests join these in milestone 3; normalization is the piece
that already exists and is most likely to silently regress.
"""

from datetime import datetime

from src import db
from src.matcher import build_artist_index, match_artist, match_events, normalize_name
from src.models import Artist, Event
from src.sources.util import LONDON_TZ


def test_lowercases():
    assert normalize_name("Aphex Twin") == "aphex twin"


def test_strips_diacritics():
    assert normalize_name("Björk") == "bjork"
    assert normalize_name("Sigur Rós") == "sigur ros"


def test_removes_leading_the():
    assert normalize_name("The Prodigy") == "prodigy"
    # "the" only stripped when leading.
    assert normalize_name("Sunburst The Band") == "sunburst the band"


def test_strips_punctuation_and_collapses_whitespace():
    assert normalize_name("Godspeed You! Black Emperor") == "godspeed you black emperor"
    assert normalize_name("  Boards   of  Canada ") == "boards of canada"


def test_combined():
    assert normalize_name("The Chemical Brothers!") == "chemical brothers"


def test_preserves_plus_as_distinct_identity():
    # "Omar+" must not collapse to "omar" - they are different artists.
    assert normalize_name("Omar+") == "omar+"
    assert normalize_name("Omar") == "omar"


def test_plus_artist_does_not_match_plain_name():
    # Following "Omar+" should not pull in an event for "Omar".
    index = build_artist_index([Artist("9", "Omar+", normalize_name("Omar+"), "followed")])
    name, score = match_artist("Omar", index)
    assert name is None


# --- matching ---------------------------------------------------------------

ARTISTS = [
    Artist("1", "Aphex Twin", normalize_name("Aphex Twin"), "followed"),
    Artist("2", "Bonobo", normalize_name("Bonobo"), "liked"),
    Artist("3", "Floating Points", normalize_name("Floating Points"), "followed"),
]
INDEX = build_artist_index(ARTISTS)


def test_match_exact_normalized():
    name, score = match_artist("The Aphex Twin", INDEX)
    assert name == "aphex twin"
    assert score == 100.0


def test_match_fuzzy_above_threshold():
    name, score = match_artist("Floating Point", INDEX)  # missing trailing 's'
    assert name == "floating points"
    assert score >= 92


def test_match_rejects_unrelated():
    name, score = match_artist("Taylor Swift", INDEX)
    assert name is None


def _event(artist: str) -> Event:
    return Event(
        source="ticketmaster",
        source_event_id="x",
        artist_name=artist,
        venue="Venue",
        city="London",
        date=datetime(2026, 7, 1, 20, tzinfo=LONDON_TZ),
        url="https://example/x",
    )


def test_match_events_keeps_and_annotates():
    events = [_event("Aphex Twin"), _event("Some Unknown Band")]
    matched = match_events(events, ARTISTS)
    assert len(matched) == 1
    assert matched[0].matched_artist == "aphex twin"


def test_match_events_logs_low_confidence(tmp_path):
    path = str(tmp_path / "m.db")
    db.init_db(path)
    # "Bonobu" ~ "bonobo" scores ~83: in [FUZZY_FLOOR, FUZZY_THRESHOLD) - logged,
    # not matched.
    with db.connect(path) as conn:
        matched = match_events([_event("Bonobu")], ARTISTS, conn=conn)
        rows = conn.execute("SELECT * FROM low_confidence_matches").fetchall()
    assert matched == []
    assert len(rows) == 1
    assert rows[0]["event_artist"] == "Bonobu"
    assert rows[0]["best_artist"] == "bonobo"
