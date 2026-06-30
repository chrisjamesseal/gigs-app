"""Weekly email digest — the final milestone.

The email is a short nudge, not a replica of the web app: it leads with the *new*
gigs found since the last digest, links to the published site for the full,
always-current list, and tucks already-seen upcoming gigs into a "still upcoming"
section. Plain-text + HTML multipart; the HTML is simple, table-based, and
dark-mode friendly (no JS).

Sending uses Resend if ``RESEND_API_KEY`` is set, otherwise SMTP (e.g. a Gmail app
password). ``--dry-run`` renders and logs the email without sending and without
marking anything as sent, so you can preview safely.

Entrypoint: ``python -m src.main --email [--dry-run]``.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import groupby

import httpx
import structlog

from . import db
from .aggregator import dedup_key
from .config import Config
from .models import Event
from .pipeline import load_upcoming

log = structlog.get_logger(__name__)

# The published site the digest links to for the full, live list.
SITE_URL = "https://chrisjamesseal.github.io/gigs-app/"

RESEND_URL = "https://api.resend.com/emails"


def _group_by_month(events: list[Event]) -> list[tuple[str, list[Event]]]:
    return [
        (label, list(group))
        for label, group in groupby(events, key=lambda e: e.date.strftime("%B %Y"))
    ]


def _split_new_seen(
    events: list[Event], new_keys: set[str]
) -> tuple[list[Event], list[Event]]:
    new = [e for e in events if dedup_key(e) in new_keys]
    seen = [e for e in events if dedup_key(e) not in new_keys]
    return new, seen


def _fmt_when(event: Event) -> str:
    return event.date.strftime("%a %d %b · %H:%M")


def _links(event: Event) -> dict[str, str]:
    return event.links or ({event.source: event.url} if event.url else {})


def subject_line(events: list[Event], new_keys: set[str]) -> str:
    new_count = len({dedup_key(e) for e in events} & new_keys)
    return f"🎧 {len(events)} London gigs this week — {new_count} new"


def render_digest(events: list[Event], new_keys: set[str]) -> tuple[str, str, str]:
    """Return ``(subject, text_body, html_body)`` for the digest."""
    new, seen = _split_new_seen(events, new_keys)
    subject = subject_line(events, new_keys)

    # --- plain text ---
    text_lines: list[str] = [subject, "", f"Full list: {SITE_URL}", ""]

    def _text_section(title: str, section: list[Event]) -> None:
        if not section:
            return
        text_lines.append(f"== {title} ==")
        for month, group in _group_by_month(section):
            text_lines.append(f"  {month}")
            for e in group:
                price = f" — from £{e.price_from:.0f}" if e.price_from else ""
                text_lines.append(f"    {_fmt_when(e)}  {e.artist_name} @ {e.venue}{price}")
                for src, url in _links(e).items():
                    text_lines.append(f"      tickets ({src}): {url}")
        text_lines.append("")

    _text_section("New this week", new)
    _text_section("Still upcoming", seen)
    text_body = "\n".join(text_lines)

    # --- html ---
    html_body = _render_html(new, seen, subject)
    return subject, text_body, html_body


def _render_html(new: list[Event], seen: list[Event], subject: str) -> str:
    def section(title: str, events: list[Event], badge: bool) -> str:
        if not events:
            return ""
        rows = [
            f'<tr><td style="padding:14px 0 6px;color:#888;font-size:12px;'
            f'text-transform:uppercase;letter-spacing:.05em;">{title}</td></tr>'
        ]
        for month, group in _group_by_month(events):
            rows.append(
                f'<tr><td style="padding:12px 0 4px;color:#a78bfa;font-size:13px;">'
                f"{month}</td></tr>"
            )
            for e in group:
                price = (
                    f'<span style="color:#bbb;font-size:13px;">from £{e.price_from:.0f}</span>'
                    if e.price_from
                    else ""
                )
                tickets = " ".join(
                    f'<a href="{url}" style="color:#a78bfa;font-size:12px;'
                    f'text-decoration:none;">tickets · {src}</a>'
                    for src, url in _links(e).items()
                )
                tag = (
                    '<span style="background:#6f3cff;color:#fff;font-size:10px;'
                    'border-radius:8px;padding:1px 6px;margin-left:6px;">NEW</span>'
                    if badge
                    else ""
                )
                rows.append(
                    '<tr><td style="padding:6px 0;border-bottom:1px solid #2a2a32;">'
                    f'<div style="font-weight:600;color:#f0f0f2;">{e.artist_name}{tag}</div>'
                    f'<div style="color:#9a9aa5;font-size:13px;">{_fmt_when(e)} · '
                    f"{e.venue or 'Venue TBA'}</div>"
                    f'<div style="margin-top:4px;">{price} {tickets}</div>'
                    "</td></tr>"
                )
        return "".join(rows)

    body = section("New this week", new, badge=True) + section(
        "Still upcoming", seen, badge=False
    )
    if not body:
        body = (
            '<tr><td style="color:#9a9aa5;padding:24px 0;">No upcoming gigs found '
            "this week.</td></tr>"
        )

    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light"></head>
<body style="margin:0;background:#0f0f12;color:#f0f0f2;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="background:#0f0f12;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="max-width:560px;">
<tr><td style="font-size:20px;font-weight:700;padding-bottom:2px;">🎧 {subject}</td></tr>
<tr><td style="padding-bottom:14px;">
<a href="{SITE_URL}" style="color:#a78bfa;font-size:14px;">View the full list →</a>
</td></tr>
{body}
<tr><td style="padding-top:20px;color:#666;font-size:11px;">
London Gig Radar · <a href="{SITE_URL}" style="color:#666;">{SITE_URL}</a></td></tr>
</table></td></tr></table></body></html>"""


def _send_via_resend(config: Config, subject: str, text: str, html: str) -> None:
    resp = httpx.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {config.resend_api_key}"},
        json={
            "from": config.email_from,
            "to": [config.email_to],
            "subject": subject,
            "text": text,
            "html": html,
        },
        timeout=httpx.Timeout(30.0),
    )
    resp.raise_for_status()
    log.info("email.sent", transport="resend", to=config.email_to)


def _send_via_smtp(config: Config, subject: str, text: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.email_from
    msg["To"] = config.email_to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.starttls()
        if config.smtp_username:
            server.login(config.smtp_username, config.smtp_password or "")
        server.send_message(msg)
    log.info("email.sent", transport="smtp", to=config.email_to)


def send_email(config: Config, subject: str, text: str, html: str) -> None:
    """Send via Resend if configured, else SMTP. Raises if neither is set up."""
    config.require("email_to", "email_from")
    if config.resend_api_key:
        _send_via_resend(config, subject, text, html)
    elif config.smtp_host:
        _send_via_smtp(config, subject, text, html)
    else:
        raise RuntimeError(
            "No email transport configured: set RESEND_API_KEY or SMTP_HOST "
            "(plus EMAIL_TO / EMAIL_FROM)."
        )


def run_digest(config: Config, *, dry_run: bool = False) -> str:
    """Build and (unless dry-run) send the weekly digest. Returns the subject.

    Reads upcoming events from the DB (populate it first via the pipeline),
    flags those not yet emailed as new, and — on a real send — marks every
    included event as sent so the next digest only highlights fresh finds.
    """
    events = load_upcoming(config)
    with db.connect(config.db_path) as conn:
        sent = db.get_sent_keys(conn)
    new_keys = {dedup_key(e) for e in events} - sent

    subject, text, html = render_digest(events, new_keys)

    if dry_run:
        log.info("email.dry_run", subject=subject, events=len(events), new=len(new_keys))
        print("\n--- EMAIL DRY RUN ---")
        print(text)
        print("--- END (not sent) ---\n")
        return subject

    send_email(config, subject, text, html)
    with db.connect(config.db_path) as conn:
        db.mark_sent(conn, {dedup_key(e) for e in events})
    return subject
