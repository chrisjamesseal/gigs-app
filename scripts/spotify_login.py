"""One-time local Spotify login to mint a refresh token (OAuth PKCE).

Run once on your own machine:

    python scripts/spotify_login.py

It opens a browser to Spotify's consent screen, then exchanges the authorization
code for tokens and prints the refresh token. Copy that token into ``.env``
(``SPOTIFY_REFRESH_TOKEN``) and, for cloud runs, into your GitHub Actions secrets.
You never have to do this again unless you revoke access.

Spotify requires an HTTPS redirect URI, which a local server can't receive, so by
default the script asks you to paste the URL you were redirected to (it contains
the code). If you registered an ``http://127.0.0.1`` loopback URI instead, the
script catches the redirect automatically. Force the paste flow with ``--manual``.

Requires ``SPOTIFY_CLIENT_ID`` and ``SPOTIFY_REDIRECT_URI`` (matching the one
registered on your Spotify app). ``SPOTIFY_CLIENT_SECRET`` is optional with PKCE
but used if present.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# Allow running as a plain script (``python scripts/spotify_login.py``).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_config  # noqa: E402
from src.spotify_client import AUTH_URL, SCOPES, exchange_code_for_tokens  # noqa: E402


def _make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636 (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None
    expected_state: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - required name
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        state = params.get("state", [None])[0]
        if state != _CallbackHandler.expected_state:
            _CallbackHandler.error = "state mismatch (possible CSRF) - aborting"
        elif "error" in params:
            _CallbackHandler.error = params["error"][0]
        else:
            _CallbackHandler.code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<h2>London Gig Radar</h2><p>Login complete - "
            "you can close this tab and return to the terminal.</p>"
            if _CallbackHandler.error is None
            else f"<h2>Login failed</h2><p>{_CallbackHandler.error}</p>"
        )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args) -> None:  # silence default stderr logging
        pass


def _is_loopback(redirect_uri: str) -> bool:
    host = urllib.parse.urlparse(redirect_uri).hostname
    return host in ("127.0.0.1", "localhost", "::1")


def _capture_code_loopback(redirect_uri: str) -> str | None:
    """Run a local server to catch the redirect (for http loopback URIs)."""
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8888
    server = HTTPServer((host, port), _CallbackHandler)
    print(f"Waiting for the redirect on {redirect_uri} ...")
    while _CallbackHandler.code is None and _CallbackHandler.error is None:
        server.handle_request()
    server.server_close()
    if _CallbackHandler.error:
        print(f"\nAuthorization failed: {_CallbackHandler.error}", file=sys.stderr)
        return None
    return _CallbackHandler.code


def _capture_code_manual(expected_state: str) -> str | None:
    """Read the authorization code by pasting the redirected URL.

    Works with any HTTPS redirect URI: after you approve, Spotify sends your
    browser to the redirect URI with ``?code=...&state=...`` in the address bar.
    Copy that whole URL (or just the code) and paste it here.
    """
    print(
        "\nAfter you click Agree, your browser lands on your redirect URL.\n"
        "Copy the FULL URL from the address bar and paste it below "
        "(it contains 'code=').\n"
    )
    pasted = input("Redirected URL (or just the code): ").strip()
    # Accept a full URL, a bare query string, or just the code itself.
    query = urllib.parse.urlparse(pasted).query or pasted
    params = urllib.parse.parse_qs(query)
    if "error" in params:
        print(f"\nAuthorization failed: {params['error'][0]}", file=sys.stderr)
        return None
    state = params.get("state", [None])[0]
    if state is not None and state != expected_state:
        print("\nState mismatch (possible CSRF). Aborting.", file=sys.stderr)
        return None
    code = params.get("code", [None])[0]
    if code:
        return code
    # They may have pasted just the raw code.
    return pasted if pasted and "=" not in pasted and "/" not in pasted else None


def main() -> int:
    config = get_config()
    config.require("spotify_client_id")
    client_id = config.spotify_client_id
    redirect_uri = config.spotify_redirect_uri

    force_manual = "--manual" in sys.argv

    verifier, challenge = _make_pkce_pair()
    state = secrets.token_urlsafe(16)
    _CallbackHandler.expected_state = state

    auth_query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    auth_url = f"{AUTH_URL}?{auth_query}"

    print("Opening your browser to authorize with Spotify...")
    print(f"If it doesn't open, visit this URL manually:\n\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # HTTPS redirect URIs (Spotify's requirement) can't be caught by a local
    # server, so fall back to pasting the redirected URL.
    if force_manual or not _is_loopback(redirect_uri):
        code = _capture_code_manual(state)
    else:
        code = _capture_code_loopback(redirect_uri)

    if not code:
        return 1

    tokens = exchange_code_for_tokens(
        client_id=client_id,
        client_secret=config.spotify_client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("\nNo refresh_token in the response:", tokens, file=sys.stderr)
        return 1

    print("\n" + "=" * 64)
    print("SUCCESS - add this to your .env and to GitHub Actions secrets:\n")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
