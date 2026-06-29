"""SQLite schema + artist caching round-trip tests."""

from src import db
from src.matcher import normalize_name
from src.models import Artist


def _artist(spotify_id: str, name: str, source: str) -> Artist:
    return Artist(
        spotify_id=spotify_id,
        name=name,
        normalized_name=normalize_name(name),
        source=source,
    )


def test_init_creates_tables(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    with db.connect(path) as conn:
        names = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"artists", "events", "sent_digests", "low_confidence_matches"} <= names


def test_upsert_and_get_artists(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    with db.connect(path) as conn:
        db.upsert_artists(
            conn,
            [_artist("1", "Björk", "followed"), _artist("2", "The XX", "liked")],
        )
    with db.connect(path) as conn:
        artists = db.get_artists(conn)

    assert len(artists) == 2
    by_id = {a.spotify_id: a for a in artists}
    assert by_id["1"].normalized_name == "bjork"
    assert by_id["2"].normalized_name == "xx"


def test_upsert_is_idempotent_and_updates(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    with db.connect(path) as conn:
        db.upsert_artists(conn, [_artist("1", "Old Name", "liked")])
    with db.connect(path) as conn:
        db.upsert_artists(conn, [_artist("1", "New Name", "followed")])
    with db.connect(path) as conn:
        artists = db.get_artists(conn)

    assert len(artists) == 1
    assert artists[0].name == "New Name"
    assert artists[0].source == "followed"
