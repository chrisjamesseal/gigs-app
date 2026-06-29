"""Email digest rendering and sending — FINAL milestone (deferred).

Sequencing decision: the email comes last, once the web app is finished. Rather
than re-rendering the full listing, the digest will be a short weekly nudge that
**links to the published web app** (the GitHub Pages URL) for the full, always-up-
to-date list — e.g. "N new London gigs this week" + a "View all" link, plus the
handful of new finds inline.

When built, the real module renders a plain-text + HTML multipart email and sends
it via Resend (or SMTP), honouring ``--dry-run`` (log instead of send), and marks
events in ``sent_digests`` so subsequent emails flag only *new* finds.

Placeholder for now so the entrypoint and project layout stay stable.
"""

from __future__ import annotations

from .models import Event

# The published site the digest links to (set when the email milestone lands;
# defaults to the gigs-app GitHub Pages URL).
SITE_URL = "https://chrisjamesseal.github.io/gigs-app/"


def render_digest(events: list[Event], new_dedup_keys: set[str]) -> tuple[str, str]:
    """Return (subject, body). Stub until the email milestone."""
    raise NotImplementedError("Email digest is the final, deferred milestone.")


def send_digest(events: list[Event], *, dry_run: bool = False) -> None:
    """Send (or, with dry_run, log) the digest. Stub until the email milestone."""
    raise NotImplementedError("Email digest is the final, deferred milestone.")
