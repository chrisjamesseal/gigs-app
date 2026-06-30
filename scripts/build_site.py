"""Build the static site published to GitHub Pages.

Renders the current upcoming gigs (from SQLite) into a self-contained
``index.html`` plus an ``events.json`` under the output directory (default
``docs/``, which GitHub Pages can serve from the ``main`` branch).

Usage:
    python scripts/build_site.py                 # build from the existing DB
    python scripts/build_site.py --refresh       # refresh from Spotify+sources first
    python scripts/build_site.py --output public # write somewhere else

In CI the workflow runs with ``--refresh`` (secrets provided) so each deploy
reflects fresh data. Locally you can build from whatever the last refresh stored.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db  # noqa: E402
from src.config import get_config  # noqa: E402
from src.logging_config import configure_logging  # noqa: E402
from src.pipeline import load_upcoming, run_pipeline  # noqa: E402
from src.web.render import (  # noqa: E402
    TEMPLATES_DIR,
    events_to_json,
    render_static_page,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs", help="Output directory.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh from Spotify + sources before building (needs secrets).",
    )
    args = parser.parse_args()

    configure_logging()
    config = get_config()
    db.init_db(config.db_path)

    if args.refresh:
        # Tolerate a not-yet-configured Spotify so the very first deploy still
        # publishes the site (and its Connect-Spotify page). Once the secrets are
        # set, the next run populates events.
        if config.spotify_refresh_token and config.spotify_client_id:
            run_pipeline(config)
        else:
            print("Spotify not configured yet; building without a refresh.")

    events = load_upcoming(config)
    with db.connect(config.db_path) as conn:
        last_run = db.get_last_run(conn)

    os.makedirs(args.output, exist_ok=True)
    html = render_static_page(events, last_run)
    with open(os.path.join(args.output, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(args.output, "events.json"), "w", encoding="utf-8") as fh:
        json.dump(events_to_json(events), fh, indent=2)
    # The Spotify OAuth callback landing page (shows the code to copy).
    callback = (TEMPLATES_DIR / "callback.html").read_text(encoding="utf-8")
    with open(os.path.join(args.output, "callback.html"), "w", encoding="utf-8") as fh:
        fh.write(callback)
    # Tell GitHub Pages not to run the content through Jekyll.
    open(os.path.join(args.output, ".nojekyll"), "w").close()

    print(
        f"Built {len(events)} events into {args.output}/ "
        "(index.html, callback.html, events.json)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
