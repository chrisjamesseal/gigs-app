"""Email digest rendering and sending — implemented in milestone 5.

Placeholder so the entrypoint and project layout are stable. The real module
renders a plain-text + HTML multipart digest grouped by month/date and sends it
via Resend (or SMTP), honouring ``--dry-run``.
"""

from __future__ import annotations

from .models import Event


def render_digest(events: list[Event], new_dedup_keys: set[str]) -> tuple[str, str]:
    """Return (subject, body). Stub until milestone 5."""
    raise NotImplementedError("Email digest is implemented in milestone 5.")


def send_digest(events: list[Event], *, dry_run: bool = False) -> None:
    """Send (or, with dry_run, log) the digest. Stub until milestone 5."""
    raise NotImplementedError("Email digest is implemented in milestone 5.")
