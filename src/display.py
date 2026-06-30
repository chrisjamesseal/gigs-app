"""Presentation helpers shared by the web app and the email digest.

Keeps display concerns (Title Case, ticket-provider labels and icons) in one place
so the app and email stay consistent.
"""

from __future__ import annotations

# Connector words kept lowercase in the middle of a title.
_SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of", "on",
    "or", "the", "to", "vs", "with", "feat", "ft", "nor", "per",
}


def _cap_word(word: str, *, force: bool) -> str:
    # Preserve already-styled tokens (any internal/leading capital): "DJ", "SBTRKT",
    # "Aphex" all stay as the artist intends.
    if any(c.isupper() for c in word):
        return word
    low = word.lower()
    if low in _SMALL_WORDS and not force:
        return low
    return word[:1].upper() + word[1:]


def titlecase(text: str | None) -> str:
    """Title-case a name for display without mangling stylized casing.

    Words that already carry a capital (e.g. "Aphex Twin", "DJ EZ") are left as-is;
    fully lowercase words are capitalized, with connector words ("of", "the", ...)
    kept lowercase unless first or last.
    """
    if not text:
        return ""
    words = text.split()
    last = len(words) - 1
    return " ".join(
        _cap_word(w, force=(i == 0 or i == last)) for i, w in enumerate(words)
    )


# Ticket provider -> (display label, domain used for the favicon).
SOURCE_META: dict[str, tuple[str, str]] = {
    "ticketmaster": ("Ticketmaster", "ticketmaster.com"),
    "bandsintown": ("Bandsintown", "bandsintown.com"),
    "skiddle": ("Skiddle", "skiddle.com"),
    "ra": ("Resident Advisor", "ra.co"),
    "dice": ("Dice", "dice.fm"),
}


def source_label(source: str) -> str:
    """Human-readable provider name, Title Cased."""
    return SOURCE_META.get(source, (titlecase(source), ""))[0]


def source_icon(source: str) -> str:
    """A small icon URL for a ticket provider (its site favicon)."""
    domain = SOURCE_META.get(source, ("", ""))[1]
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
