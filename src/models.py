"""Shared dataclasses used across sources, the matcher, and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Artist:
    spotify_id: str
    name: str
    normalized_name: str  # lowercased, accents stripped, "the" removed
    source: Literal["followed", "liked"]
    image_url: str | None = None  # Spotify artist photo, for display


@dataclass
class Event:
    source: str  # "ticketmaster" | "bandsintown" | "skiddle" | "ra" | "dice"
    source_event_id: str  # for dedup within a source
    artist_name: str  # as returned by the source
    venue: str
    city: str
    date: datetime  # timezone-aware, Europe/London
    url: str
    matched_artist: str | None = None  # normalized name that matched
    price_from: float | None = None
    fetched_at: datetime | None = None
    links: dict[str, str] = field(default_factory=dict)  # source -> url, set on dedup
    image_url: str | None = None  # artist photo, populated for display from the DB
