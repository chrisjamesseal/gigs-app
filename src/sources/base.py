"""Source protocol and the error boundary every source is wrapped in.

A source is any callable matching :class:`Source`:

    def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]

The cardinal rule (spec): *a failed source logs and returns ``[]``* - it must never
take down the whole digest. :func:`safe_fetch` enforces that boundary so individual
source modules can be written as if the network always behaves.
"""

from __future__ import annotations

import time
from typing import Callable, Protocol

import structlog

from ..models import Event

log = structlog.get_logger(__name__)

Source = Callable[[list[str], str], list["Event"]]


class SupportsFetchEvents(Protocol):
    def fetch_events(
        self, artist_names: list[str], location: str = "London"
    ) -> list[Event]: ...


def safe_fetch(
    name: str,
    fetch: Source,
    artist_names: list[str],
    location: str = "London",
) -> tuple[list[Event], bool]:
    """Run a source's fetch, catching everything.

    Returns ``(events, ok)`` where ``ok`` is False if the source raised - the
    caller uses that to flag partial coverage in the digest, without conflating a
    crash with a source that legitimately found nothing. On failure the events
    list is empty, honouring the spec's "a failed source returns ``[]``" rule.

    Emits one structured log line per source with ``events_found``, ``duration_ms``,
    and any error - the observability contract from the spec.
    """
    start = time.monotonic()
    try:
        events = fetch(artist_names, location)
        log.info(
            "source.ok",
            source=name,
            events_found=len(events),
            duration_ms=round((time.monotonic() - start) * 1000),
        )
        return events, True
    except Exception as exc:  # noqa: BLE001 - boundary is deliberately broad
        log.error(
            "source.failed",
            source=name,
            duration_ms=round((time.monotonic() - start) * 1000),
            errors=str(exc),
        )
        return [], False
