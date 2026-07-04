"""Shared rendering helpers for both the live app and the static-site build.

Kept free of any FastAPI import so the GitHub Pages build step stays lean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..display import source_icon, source_label, titlecase
from ..matcher import normalize_name
from ..models import Event

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class Occurrence:
    """One date of a gig, with its own ticket links and price."""

    date: datetime
    price_from: float | None
    links: dict[str, str]  # source -> url


@dataclass
class GigCard:
    """An artist at a venue, holding one or more dates (occurrences).

    When an artist plays the same venue on several days, those dates are merged
    into a single card so the list shows one entry with a button per night.
    """

    artist_name: str
    venue: str
    city: str
    image_url: str | None
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def date(self) -> datetime:
        """Earliest date, used for month bucketing and sorting."""
        return self.occurrences[0].date

    @property
    def multi(self) -> bool:
        return len(self.occurrences) > 1


def configure_jinja(env: Environment) -> Environment:
    """Register the shared display filters/globals on a Jinja environment."""
    env.filters["titlecase"] = titlecase
    env.globals["source_label"] = source_label
    env.globals["source_icon"] = source_icon
    return env


_env = configure_jinja(
    Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
)


def _occurrence(event: Event) -> Occurrence:
    links = event.links if event.links else ({event.source: event.url} if event.url else {})
    return Occurrence(date=event.date, price_from=event.price_from, links=links)


def cards_from_events(events: list[Event]) -> list[GigCard]:
    """Collapse date-sorted events into gig cards.

    Events sharing an artist and venue are merged into one card carrying each
    date as a separate occurrence. Input is assumed sorted by date ascending, so
    each card's occurrences (and the cards themselves) come out soonest-first.
    """
    cards: dict[tuple[str, str], GigCard] = {}
    order: list[tuple[str, str]] = []
    for event in events:
        key = (
            event.matched_artist or normalize_name(event.artist_name),
            normalize_name(event.venue),
        )
        card = cards.get(key)
        if card is None:
            card = GigCard(
                artist_name=event.artist_name,
                venue=event.venue,
                city=event.city,
                image_url=event.image_url,
                occurrences=[_occurrence(event)],
            )
            cards[key] = card
            order.append(key)
        else:
            card.occurrences.append(_occurrence(event))
            if card.image_url is None and event.image_url:
                card.image_url = event.image_url
    return [cards[k] for k in order]


def group_by_month(events: list[Event]) -> list[tuple[str, list[GigCard]]]:
    """Group date-sorted events into [(month label, [gig cards]), ...]."""
    cards = cards_from_events(events)
    return [
        (label, list(group))
        for label, group in groupby(cards, key=lambda c: c.date.strftime("%B %Y"))
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
            "artist": titlecase(e.artist_name),
            "matched_artist": e.matched_artist,
            "venue": titlecase(e.venue),
            "city": titlecase(e.city),
            "date": e.date.isoformat(),
            "price_from": e.price_from,
            "url": e.url,
            "links": e.links,
            "image_url": e.image_url,
            "source": e.source,
        }
        for e in events
    ]
