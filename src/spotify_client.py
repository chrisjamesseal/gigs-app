"""Spotify Web API client.

Authentication is OAuth 2.0 Authorization Code with PKCE. A one-time local login
(``scripts/spotify_login.py``) mints a long-lived refresh token; from then on the
job exchanges that refresh token for short-lived access tokens with no human in
the loop.

Milestone 1 surface:
- :func:`refresh_access_token` — refresh-token -> access-token.
- :func:`exchange_code_for_tokens` — used by the login script (PKCE code exchange).
- :func:`fetch_artists` — followed + liked-song artists, deduped to ``Artist``.
"""

from __future__ import annotations

import base64

import httpx
import structlog

from .config import Config
from .matcher import normalize_name
from .models import Artist

log = structlog.get_logger(__name__)

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
SCOPES = "user-follow-read user-library-read"

_TIMEOUT = httpx.Timeout(30.0)


def _basic_auth_header(client_id: str, client_secret: str) -> dict[str, str]:
    raw = f"{client_id}:{client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def exchange_code_for_tokens(
    *,
    client_id: str,
    client_secret: str | None,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Exchange an authorization code (+ PKCE verifier) for access/refresh tokens.

    Returns the raw token response dict (includes ``access_token`` and
    ``refresh_token``). Used by the one-time login script.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_secret:
        headers.update(_basic_auth_header(client_id, client_secret))

    resp = httpx.post(TOKEN_URL, data=data, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(
    *, client_id: str, client_secret: str | None, refresh_token: str
) -> str:
    """Exchange a stored refresh token for a fresh access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_secret:
        headers.update(_basic_auth_header(client_id, client_secret))

    resp = httpx.post(TOKEN_URL, data=data, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["access_token"]


def access_token_from_config(config: Config) -> str:
    """Resolve an access token from the configured refresh token."""
    config.require("spotify_client_id", "spotify_refresh_token")
    return refresh_access_token(
        client_id=config.spotify_client_id,  # type: ignore[arg-type]
        client_secret=config.spotify_client_secret,
        refresh_token=config.spotify_refresh_token,  # type: ignore[arg-type]
    )


def _paginated_get(
    client: httpx.Client, url: str, params: dict | None = None
) -> list[dict]:
    """Follow Spotify ``next`` pagination, returning the merged ``items``.

    Handles both top-level paging objects (``/me/tracks``) and the
    artist-wrapped shape used by ``/me/following`` (``{"artists": {...}}``).
    """
    items: list[dict] = []
    next_url: str | None = url
    next_params: dict | None = params
    while next_url:
        resp = client.get(next_url, params=next_params)
        resp.raise_for_status()
        payload = resp.json()
        page = payload.get("artists", payload)  # /me/following nests under "artists"
        items.extend(page.get("items", []))
        next_url = page.get("next")
        next_params = None  # ``next`` is a fully-formed URL
    return items


def get_followed_artists(client: httpx.Client) -> list[Artist]:
    """Followed artists via ``GET /me/following?type=artist``."""
    raw = _paginated_get(
        client, f"{API_BASE}/me/following", params={"type": "artist", "limit": 50}
    )
    artists: list[Artist] = []
    for a in raw:
        if not a or not a.get("id"):
            continue
        artists.append(
            Artist(
                spotify_id=a["id"],
                name=a["name"],
                normalized_name=normalize_name(a["name"]),
                source="followed",
            )
        )
    return artists


def get_liked_song_artists(client: httpx.Client) -> list[Artist]:
    """Artists drawn from saved tracks via ``GET /me/tracks``."""
    raw = _paginated_get(client, f"{API_BASE}/me/tracks", params={"limit": 50})
    artists: list[Artist] = []
    for item in raw:
        track = (item or {}).get("track") or {}
        for a in track.get("artists", []):
            if not a.get("id"):
                continue
            artists.append(
                Artist(
                    spotify_id=a["id"],
                    name=a["name"],
                    normalized_name=normalize_name(a["name"]),
                    source="liked",
                )
            )
    return artists


def _dedup(artists: list[Artist]) -> list[Artist]:
    """Dedup by spotify_id, preferring a 'followed' record over 'liked'."""
    by_id: dict[str, Artist] = {}
    for a in artists:
        existing = by_id.get(a.spotify_id)
        if existing is None:
            by_id[a.spotify_id] = a
        elif existing.source == "liked" and a.source == "followed":
            by_id[a.spotify_id] = a
    return sorted(by_id.values(), key=lambda x: x.name.lower())


def fetch_artists(config: Config) -> list[Artist]:
    """Fetch followed + liked-song artists, deduped to a single ``Artist`` list."""
    access_token = access_token_from_config(config)
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(headers=headers, timeout=_TIMEOUT) as client:
        followed = get_followed_artists(client)
        liked = get_liked_song_artists(client)

    merged = _dedup(followed + liked)
    log.info(
        "spotify.artists_fetched",
        followed=len(followed),
        liked=len(liked),
        deduped=len(merged),
    )
    return merged
