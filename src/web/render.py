"""Shared rendering helpers for both the live app and the static-site build.

Kept free of any FastAPI import so the GitHub Pages build step stays lean.
"""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Event

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def group_by_month(events: list[Event]) -> list[tuple[str, list[Event]]]:
    """Group date-sorted events into [(month label, [events]), ...]."""
    return [
        (label, list(group))
        for label, group in groupby(events, key=lambda e: e.date.strftime("%B %Y"))
    ]


def render_static_page(events: list[Event], last_run: dict | None) -> str:
    """Render the gig list to a self-contained static HTML string (GitHub Pages)."""
    template = _env.get_template("index.html")
    return template.render(
        groups=group_by_month(events),
        total=len(events),
        last_run=last_run,
        static=True,
        refreshing=False,
        error=None,
        spotify_ready=True,
    )


def events_to_json(events: list[Event]) -> list[dict]:
    """Serialize events to plain dicts for the published ``events.json``."""
    return [
        {
            "artist": e.artist_name,
            "matched_artist": e.matched_artist,
            "venue": e.venue,
            "city": e.city,
            "date": e.date.isoformat(),
            "price_from": e.price_from,
            "url": e.url,
            "links": e.links,
            "source": e.source,
        }
        for e in events
    ]
