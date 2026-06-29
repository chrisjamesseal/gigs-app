"""FastAPI application serving the gig list and a refresh trigger.

Page loads only ever read from SQLite — they never hit the network. Refreshing the
data (Spotify + sources) is an explicit action (``POST /refresh``) that runs the
shared pipeline in a background thread so the request returns immediately; the page
shows a "refreshing…" banner until it finishes.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import get_config
from ..pipeline import load_upcoming, run_pipeline
from .render import events_to_json, group_by_month

log = structlog.get_logger(__name__)

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="London Gig Radar")


class RefreshState:
    """Tracks the background refresh so the UI can reflect progress/errors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.error: str | None = None

    def start(self) -> bool:
        """Begin a refresh if one isn't already running. Returns True if started."""
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.error = None
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return True

    def _run(self) -> None:
        try:
            run_pipeline(get_config())
        except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
            log.error("web.refresh_failed", error=str(exc))
            with self._lock:
                self.error = str(exc)
        finally:
            with self._lock:
                self.running = False


refresh_state = RefreshState()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    config = get_config()
    events = load_upcoming(config)
    from .. import db

    with db.connect(config.db_path) as conn:
        last_run = db.get_last_run(conn)

    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "groups": group_by_month(events),
            "total": len(events),
            "last_run": last_run,
            "static": False,
            "refreshing": refresh_state.running,
            "error": refresh_state.error,
            "spotify_ready": bool(config.spotify_refresh_token),
            "now": datetime.now().astimezone(),
        },
    )


@app.post("/refresh")
def refresh() -> RedirectResponse:
    refresh_state.start()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/events")
def api_events() -> JSONResponse:
    """JSON list of upcoming events, for programmatic/mobile use."""
    config = get_config()
    events = load_upcoming(config)
    return JSONResponse(events_to_json(events))


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
