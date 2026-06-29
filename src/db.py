"""SQLite schema and helpers.

A single SQLite file (path from ``DB_PATH``) holds everything: the cached artist
list, fetched events, the dedup-aware sent-digest log, and a low-confidence match
log for diagnosing the matcher. All access goes through helpers here so the schema
lives in exactly one place.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from .models import Artist, Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    spotify_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('followed', 'liked')),
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artists_normalized ON artists (normalized_name);

CREATE TABLE IF NOT EXISTS events (
    source          TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    artist_name     TEXT NOT NULL,
    matched_artist  TEXT,
    venue           TEXT NOT NULL,
    city            TEXT NOT NULL,
    date            TEXT NOT NULL,          -- ISO 8601, tz-aware Europe/London
    url             TEXT NOT NULL,
    price_from      REAL,
    fetched_at      TEXT NOT NULL,
    links           TEXT NOT NULL DEFAULT '{}',
    dedup_key       TEXT NOT NULL,          -- (normalized_artist, date, normalized_venue)
    PRIMARY KEY (source, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_events_dedup ON events (dedup_key);
CREATE INDEX IF NOT EXISTS idx_events_date ON events (date);

CREATE TABLE IF NOT EXISTS sent_digests (
    dedup_key TEXT PRIMARY KEY,
    sent_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS low_confidence_matches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_artist  TEXT NOT NULL,
    best_artist   TEXT,
    score         REAL,
    source        TEXT,
    logged_at     TEXT NOT NULL
);
"""


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Yield a connection with sensible pragmas, committing on clean exit."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    """Create all tables if they do not already exist."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def upsert_artists(conn: sqlite3.Connection, artists: Iterable[Artist]) -> int:
    """Insert or update cached artists; returns the number written."""
    now = datetime.now().astimezone().isoformat()
    rows = [
        (a.spotify_id, a.name, a.normalized_name, a.source, now) for a in artists
    ]
    conn.executemany(
        """
        INSERT INTO artists (spotify_id, name, normalized_name, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(spotify_id) DO UPDATE SET
            name = excluded.name,
            normalized_name = excluded.normalized_name,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        rows,
    )
    return len(rows)


def get_artists(conn: sqlite3.Connection) -> list[Artist]:
    """Return all cached artists."""
    cur = conn.execute(
        "SELECT spotify_id, name, normalized_name, source FROM artists ORDER BY name"
    )
    return [
        Artist(
            spotify_id=row["spotify_id"],
            name=row["name"],
            normalized_name=row["normalized_name"],
            source=row["source"],
        )
        for row in cur.fetchall()
    ]


def upsert_event(conn: sqlite3.Connection, event: Event, dedup_key: str) -> None:
    """Insert or update a single event keyed by (source, source_event_id)."""
    conn.execute(
        """
        INSERT INTO events (
            source, source_event_id, artist_name, matched_artist, venue, city,
            date, url, price_from, fetched_at, links, dedup_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, source_event_id) DO UPDATE SET
            artist_name = excluded.artist_name,
            matched_artist = excluded.matched_artist,
            venue = excluded.venue,
            city = excluded.city,
            date = excluded.date,
            url = excluded.url,
            price_from = excluded.price_from,
            fetched_at = excluded.fetched_at,
            links = excluded.links,
            dedup_key = excluded.dedup_key
        """,
        (
            event.source,
            event.source_event_id,
            event.artist_name,
            event.matched_artist,
            event.venue,
            event.city,
            event.date.isoformat(),
            event.url,
            event.price_from,
            (event.fetched_at or datetime.now().astimezone()).isoformat(),
            json.dumps(event.links),
            dedup_key,
        ),
    )


def log_low_confidence(
    conn: sqlite3.Connection,
    *,
    event_artist: str,
    best_artist: str | None,
    score: float | None,
    source: str | None,
) -> None:
    """Record a near-miss artist match for later inspection."""
    conn.execute(
        """
        INSERT INTO low_confidence_matches
            (event_artist, best_artist, score, source, logged_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_artist,
            best_artist,
            score,
            source,
            datetime.now().astimezone().isoformat(),
        ),
    )
