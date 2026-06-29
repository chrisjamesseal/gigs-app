# London Gig Radar

A personal **web app** listing every upcoming London gig by artists you follow or
have liked songs from on Spotify. A scheduled job pulls your Spotify artists,
queries multiple gig sources, matches and dedups the results, and publishes a
mobile-friendly page to **GitHub Pages** — refreshed automatically.

Single-user personal tool — no ticket buying, no multi-user support. (The web app
replaced the originally-planned email digest; the email code remains in the repo
for a later milestone.)

## How it runs

- **Live (local):** `python -m src.web` serves the list with a working **Refresh**
  button — open it from your phone over home WiFi.
- **Published (GitHub Pages):** a daily GitHub Actions job rebuilds a static
  `index.html` from fresh data and deploys it, so you can browse from anywhere at
  <https://chrisjamesseal.github.io/gigs-app/>.

> **Privacy note:** a GitHub Pages site is public, so your published gig list (and
> `events.json`) is publicly viewable. It exposes gigs/artists, not your account.
> Keep it in mind; all API keys stay in repo secrets and are never published.

## Status

This repo is built milestone-by-milestone (see [Roadmap](#roadmap)).

**✅ Milestone 1 — Skeleton:** project layout, config loader, SQLite schema, and a
one-time Spotify login that mints a refresh token.

**✅ Milestone 2 — Two easy sources:** Ticketmaster (Discovery API) and Bandsintown,
with artist matching (exact + fuzzy). Bandsintown results are filtered to London by
city name or within 30km of the centre.

**✅ Milestone 3 — Matcher + dedup + storage:** events are matched, deduped across
sources on `(artist, date, venue)` (merging each source's ticket link), and stored
in SQLite.

**✅ Web app:** a mobile-friendly list of upcoming gigs, served live with a Refresh
button (`python -m src.web`) and published as a static site to GitHub Pages via CI.
This is the primary deliverable.

**✅ Milestone 5 — Skiddle:** third API source, covering live gigs and
club/electronic nights (geo-constrained to ~15km of central London).

**✅ Milestone 6 — RA + Dice scrapers (current):** isolated, kill-switched,
defensively-parsed scrapers for Resident Advisor and Dice. These are *best-effort*
and need a one-time live-query verification — see
[REFRESHING_SCRAPERS.md](REFRESHING_SCRAPERS.md).

The optional email digest is the only remaining later milestone.

## Quick start

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (or `poetry`).

```bash
# 1. Install dependencies into a local venv.
uv venv
uv pip install -e ".[dev]"

# 2. Configure.
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID (and SPOTIFY_CLIENT_SECRET if your app has one).

# 3. One-time Spotify login — mints a refresh token (opens a browser).
python scripts/spotify_login.py
# Paste the printed SPOTIFY_REFRESH_TOKEN into .env.

# 4. Fetch gigs into the database, then browse them in the web app.
python -m src.main            # populate the SQLite DB
python -m src.web             # open http://localhost:8000
```

### Spotify app setup

1. Create an app at <https://developer.spotify.com/dashboard>.
2. Add `http://127.0.0.1:8888/callback` as a Redirect URI (must match
   `SPOTIFY_REDIRECT_URI`).
3. Copy the Client ID (and Client Secret, if shown) into `.env`.
4. Run `scripts/spotify_login.py` once to authorize the scopes
   `user-follow-read` and `user-library-read` and mint a refresh token.

The refresh token is long-lived: store it in `.env` locally and, for cloud runs,
as a GitHub Actions secret. You never repeat the login unless you revoke access.

## Usage

### Web app (local)

```bash
python -m src.web                 # serve at http://0.0.0.0:8000
# Open http://<your-computer-ip>:8000 on your phone (same WiFi).
# Hit "Refresh" to pull the latest gigs (needs Spotify + source keys).
```

### Headless pipeline (populate the database / cron)

```bash
python -m src.main                      # refresh artists + sources, store, print
python -m src.main --no-refresh-artists # reuse the cached Spotify artist list
```

### Build the static site

```bash
python scripts/build_site.py --refresh  # refresh data, write docs/index.html + events.json
python scripts/build_site.py            # rebuild from the existing DB only
```

## Deploying to GitHub Pages

Same hosting model as the map app — a static site built and pushed by CI:

1. In the repo, **Settings → Pages → Build and deployment → Source: GitHub
   Actions**.
2. Add your keys under **Settings → Secrets and variables → Actions**:
   `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`,
   `TICKETMASTER_API_KEY`, `BANDSINTOWN_APP_ID`, `SKIDDLE_API_KEY`.
3. The [`pages.yml`](.github/workflows/pages.yml) workflow runs daily (and on
   demand via **Actions → Build & deploy site → Run workflow**, or on push to
   `main`). It refreshes the data and deploys `docs/` to Pages.

The published URL is <https://chrisjamesseal.github.io/gigs-app/>.

## Project layout

```
src/
├── main.py            # CLI entrypoint (populate the DB / cron)
├── config.py          # env/.env config loader
├── db.py              # SQLite schema + helpers
├── models.py          # Artist / Event dataclasses
├── matcher.py         # name normalization + fuzzy matching
├── spotify_client.py  # Spotify OAuth + artist fetch
├── aggregator.py      # fan out across sources + cross-source dedup
├── pipeline.py        # shared refresh: fetch -> match -> dedup -> store
├── emailer.py         # digest rendering/sending (later milestone)
├── sources/           # one isolated module per gig source
└── web/               # FastAPI app + static-site renderer + templates
scripts/
├── spotify_login.py   # one-time refresh-token minting (PKCE)
└── build_site.py      # render the static site for GitHub Pages
.github/workflows/
└── pages.yml          # daily build + deploy to GitHub Pages
tests/
```

## Configuration

All config comes from environment variables (or a local `.env`). See
[`.env.example`](.env.example) for the full list. Real environment variables take
precedence over `.env`, so GitHub Actions secrets override local values.

## Development

```bash
uv pip install -e ".[dev]"
python -m pytest
```

## A note on the RA and Dice scrapers

Resident Advisor and Dice have **no public API.** Those sources are
reverse-engineered from their web apps, live in a ToS grey area, and **will break
without warning.** They are built on a strictly best-effort basis:

- Each is an isolated module with defensive parsing; on any failure it returns no
  events (also wrapped by `safe_fetch`), and the rest of the app carries on.
- Each has a kill switch (`RA_ENABLED` / `DICE_ENABLED`) to disable it instantly.

When (not if) they stop working, the site still updates with the remaining
sources, plus a banner noting that coverage was partial. Don't be surprised — this
is by design. To re-capture their request shapes, see
[REFRESHING_SCRAPERS.md](REFRESHING_SCRAPERS.md).

## Roadmap

1. **Skeleton** — repo layout, config, SQLite schema, Spotify login. ← *done*
2. **Two easy sources** — Ticketmaster + Bandsintown. ← *done*
3. **Matcher + dedup + storage** — events in SQLite, dedup tested. ← *done*
4. **Web app** — mobile list, live Refresh, static GitHub Pages deploy. ← *done*
5. **Skiddle** — third API source. ← *done*
6. **RA + Dice scrapers** — isolated, with kill switches. ← *done*
7. **Email digest (final)** — a short weekly nudge that **links to the web app**
   for the full list; built last, once the web app is done.
