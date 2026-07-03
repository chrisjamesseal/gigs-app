# Refreshing the RA & Dice scrapers

Resident Advisor and Dice have **no public API**. The `ra` and `dice` sources talk
to the private endpoints their own websites/apps use. These are reverse-engineered,
sit in a ToS grey area, and **will break without warning** when either site changes
its schema. They are best-effort by design: if one breaks, it returns no events and
the rest of the app (Ticketmaster, Bandsintown, Skiddle) carries on, with a banner
noting partial coverage.

Both have kill switches in `.env` - set `RA_ENABLED=false` or `DICE_ENABLED=false`
to disable instantly.

When a scraper stops returning events, re-capture its current request shape:

## Resident Advisor (`src/sources/ra.py`)

1. Open an RA London events listing in a desktop browser
   (e.g. <https://ra.co/events/uk/london>).
2. Open DevTools → **Network** → filter to `graphql`.
3. Reload; find the `POST https://ra.co/graphql` request whose payload contains an
   event-listings query.
4. Copy the **query** string into `GET_EVENT_LISTINGS`, and align the **variables**
   (area id, date filter, paging) with `_variables()`.
5. Update `parse_events()` if the response field names changed (it reads
   `data.eventListings.data[].event.{id,title,date,startTime,contentUrl,venue.name,
   artists[].name}`).
6. Update `tests/fixtures/ra_sample.json` to a real (trimmed) response and run
   `pytest tests/test_sources.py`.

The London RA area id is currently `13`; verify it hasn't changed.

## Dice (`src/sources/dice.py`)

The Dice scraper fetches their website HTML (search pages) and parses embedded
JSON data (`__NEXT_DATA__` or JSON-LD structured data) rather than calling a
private REST API. This is more resilient to API versioning changes.

1. Open <https://dice.fm/search?query=bicep&type=events> in a browser.
2. View Page Source and search for `__NEXT_DATA__` or `application/ld+json`.
3. Check the JSON structure matches what `parse_html()` expects: events with
   `{id, date/startDate, venue.name, venue.city, summary_lineup[].name,
   permalink/url, price}`.
4. If the data shape changed, update `_parse_next_data()` or `_parse_jsonld()`.
5. Update `tests/fixtures/dice_page.html` and run `pytest tests/test_sources.py`.

## Why parsing is defensive

Both parsers are written so that an unexpected shape yields *fewer events*, never an
exception - so a partial schema drift degrades gracefully instead of taking down a
refresh. The network call itself is additionally wrapped by `safe_fetch` in the
aggregator, which catches everything and returns `[]` on failure.
