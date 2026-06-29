# London Gig Radar

A zero-touch weekly email: *"Here are gigs in London by artists you care about in
the next 90 days."* It pulls your followed and liked-song artists from Spotify,
queries multiple gig sources, and emails a digest. Designed to run for free on a
GitHub Actions cron.

Single-user personal tool — no web UI, no ticket buying, no multi-user support.

## Status

This repo is built milestone-by-milestone (see [Roadmap](#roadmap)).

**✅ Milestone 1 — Skeleton:** project layout, config loader, SQLite schema, and a
one-time Spotify login that mints a refresh token.

**✅ Milestone 2 — Two easy sources (current):** Ticketmaster (Discovery API) and
Bandsintown wired up, with artist matching (exact + fuzzy). Running the entrypoint
now fetches your artists, queries both sources for London events, matches them
back to your artists, and prints the gigs to the console. Bandsintown results are
filtered to London by city name or within 30km of the centre.

Skiddle, the RA/Dice scrapers, dedup+storage, the email digest, and the cron
deploy arrive in later milestones; their modules exist as stubs so the structure
is stable.

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

# 4. Run the pipeline. Milestone 1 prints your followed + liked artists.
python -m src.main
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

```bash
python -m src.main                      # refresh artists from Spotify, then run
python -m src.main --no-refresh-artists # use the cached artist list in SQLite
python -m src.main --dry-run            # never send email (log it instead)
```

## Project layout

```
src/
├── main.py            # entrypoint
├── config.py          # env/.env config loader
├── db.py              # SQLite schema + helpers
├── models.py          # Artist / Event dataclasses
├── matcher.py         # name normalization (+ fuzzy matching, later)
├── spotify_client.py  # Spotify OAuth + artist fetch
├── aggregator.py      # fan out artists across sources
├── emailer.py         # digest rendering/sending (milestone 5)
└── sources/           # one isolated module per gig source
scripts/
└── spotify_login.py   # one-time refresh-token minting (PKCE)
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

- Each is an isolated module wrapped in a top-level try/except — if it breaks it
  logs and returns no events, and the rest of the digest carries on.
- Each has a kill switch (`RA_ENABLED` / `DICE_ENABLED`) to disable it instantly.

When (not if) they stop working, the weekly email still goes out with the
remaining sources, plus a footer noting that coverage was partial. Don't be
surprised — this is by design.

## Roadmap

1. **Skeleton** — repo layout, config, SQLite schema, Spotify login. ← *done*
2. **Two easy sources** — Ticketmaster + Bandsintown. ← *done*
3. **Matcher + dedup + storage** — events in SQLite, dedup tested.
4. **Skiddle** — third API source.
5. **Email digest** — dry-run locally, then for real.
6. **RA + Dice scrapers** — isolated, with kill switches.
7. **GitHub Actions deploy** — weekly cron, secrets, persisted DB.
8. **Polish** — observability, low-confidence match log, README.
