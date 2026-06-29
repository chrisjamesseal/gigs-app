"""Artist-name normalization and matching.

Milestone 1 only needs :func:`normalize_name` (used when caching Spotify artists).
The fuzzy matching machinery (``match_event_artist`` and friends) lands in
milestone 3 alongside its tests; it is defined here so the public surface is
stable, but is intentionally simple for now.
"""

from __future__ import annotations

import re
import unicodedata

_LEADING_THE = re.compile(r"^the\s+")
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


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
