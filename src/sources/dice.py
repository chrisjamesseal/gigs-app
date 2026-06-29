"""dice source — implemented in a later milestone.

Stub conforming to the source contract: returns no events for now so the
aggregator can wire it up without special-casing. See the spec's milestone list.
"""

from __future__ import annotations

from ..models import Event


def fetch_events(artist_names: list[str], location: str = "London") -> list[Event]:
    return []
