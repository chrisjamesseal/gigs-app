"""Central configuration loaded from the environment / a local ``.env`` file.

Reading config goes through :func:`get_config` so the rest of the codebase never
touches ``os.environ`` directly. Values absent from the environment fall back to
the documented defaults below; required-but-missing values raise when first read
via :meth:`Config.require`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # Spotify
    spotify_client_id: str | None
    spotify_client_secret: str | None
    spotify_refresh_token: str | None
    spotify_redirect_uri: str

    # Gig sources (used in later milestones)
    ticketmaster_api_key: str | None
    bandsintown_app_id: str | None
    skiddle_api_key: str | None

    # Scraper kill switches
    ra_enabled: bool
    dice_enabled: bool

    # Email
    email_to: str | None
    email_from: str | None
    resend_api_key: str | None
    # SMTP fallback (e.g. Gmail app password) - used if no Resend key is set.
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None

    # Behaviour
    lookahead_days: int
    db_path: str

    _present: frozenset[str] = field(default_factory=frozenset, repr=False)

    def require(self, *names: str) -> None:
        """Raise if any of the named config attributes are unset/empty."""
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(
                "Missing required configuration: "
                + ", ".join(sorted(missing))
                + ". Set them in your environment or .env file "
                "(see .env.example)."
            )


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load configuration once and cache it for the process lifetime."""
    # Load .env if present; real environment variables take precedence.
    load_dotenv(override=False)

    return Config(
        spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID") or None,
        spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET") or None,
        spotify_refresh_token=os.getenv("SPOTIFY_REFRESH_TOKEN") or None,
        spotify_redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ),
        ticketmaster_api_key=os.getenv("TICKETMASTER_API_KEY") or None,
        bandsintown_app_id=os.getenv("BANDSINTOWN_APP_ID") or None,
        skiddle_api_key=os.getenv("SKIDDLE_API_KEY") or None,
        ra_enabled=_as_bool(os.getenv("RA_ENABLED"), True),
        dice_enabled=_as_bool(os.getenv("DICE_ENABLED"), True),
        email_to=os.getenv("EMAIL_TO") or None,
        email_from=os.getenv("EMAIL_FROM") or None,
        resend_api_key=os.getenv("RESEND_API_KEY") or None,
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=_as_int(os.getenv("SMTP_PORT"), 587),
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        lookahead_days=_as_int(os.getenv("LOOKAHEAD_DAYS"), 90),
        db_path=os.getenv("DB_PATH", "gig_radar.db"),
    )
