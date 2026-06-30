"""Artist-name normalization and matching.

:func:`normalize_name` is used when caching Spotify artists. The matching layer
(:func:`match_artist`, :func:`match_events`) resolves an event's artist string
back to one of the user's Spotify artists: exact match on the normalized name, or
``rapidfuzz`` ratio >= 92 as a probable match. Near-misses below that are dropped
but logged to ``low_confidence_matches`` so systemic gaps (e.g. "Aphex Twin" vs
"AFX") surface over time.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

import structlog
from rapidfuzz import fuzz, process

from .db import log_low_confidence
from .models import Artist, Event

log = structlog.get_logger(__name__)

_LEADING_THE = re.compile(r"^the\s+")
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")

# A fuzzy ratio at/above this is a probable match; below FUZZY_FLOOR isn't even
# worth logging (almost certainly a different artist).
FUZZY_THRESHOLD = 92
FUZZY_FLOOR = 80


def normalize_name(name: str) -> str:
    """Normalize an artist name for comparison.

    Lowercase, strip diacritics, drop a leading "the ", remove punctuation, and
    collapse whitespace. ``"The Blødüd Brønç!"`` -> ``"blodud bronc"``.
    """
    # Decompose accents and drop combining marks.
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))

    lowered = stripped.lower().strip()
    lowered = _LEADING_THE.sub("", lowered)
    lowered = _PUNCT.sub(" ", lowered)
    lowered = _WS.sub(" ", lowered).strip()
    return lowered


def build_artist_index(artists: list[Artist]) -> dict[str, str]:
    """Map normalized_name -> display name for the user's artists."""
    return {a.normalized_name: a.name for a in artists}


def match_artist(event_artist: str, index: dict[str, str]) -> tuple[str | None, float]:
    """Resolve an event's artist string to a known normalized name.

    Returns ``(normalized_name | None, score)``. ``score`` is 100 for an exact
    normalized match, otherwise the best fuzzy ratio considered (so the caller can
    decide whether a miss is worth logging).
    """
    norm = normalize_name(event_artist)
    if not norm or not index:
        return None, 0.0
    if norm in index:
        return norm, 100.0

    best = process.extractOne(norm, index.keys(), scorer=fuzz.ratio)
    if best is None:
        return None, 0.0
    candidate, score, _ = best
    if score >= FUZZY_THRESHOLD:
        return candidate, float(score)
    return None, float(score)


def match_events(
    events: list[Event],
    artists: list[Artist],
    *,
    conn: sqlite3.Connection | None = None,
) -> list[Event]:
    """Annotate and return only the events whose artist matched a known artist.

    Sets ``matched_artist`` on each kept event. Near-misses in
    ``[FUZZY_FLOOR, FUZZY_THRESHOLD)`` are logged to ``low_confidence_matches``
    when a connection is supplied.
    """
    index = build_artist_index(artists)
    matched: list[Event] = []
    for event in events:
        name, score = match_artist(event.artist_name, index)
        if name is not None:
            event.matched_artist = name
            matched.append(event)
            if score < 100:
                log.info(
                    "match.fuzzy",
                    event_artist=event.artist_name,
                    matched=name,
                    score=score,
                    source=event.source,
                )
        elif score >= FUZZY_FLOOR:
            best = process.extractOne(
                normalize_name(event.artist_name), index.keys(), scorer=fuzz.ratio
            )
            if conn is not None:
                log_low_confidence(
                    conn,
                    event_artist=event.artist_name,
                    best_artist=best[0] if best else None,
                    score=score,
                    source=event.source,
                )
    return matched
