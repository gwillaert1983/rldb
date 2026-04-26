# RLDB

Privé dashboard dat redlights.be scrapet en profielen opslaat.

## Stack

- **Backend**: FastAPI + SQLAlchemy ORM
- **Database**: Turso (libSQL/SQLite-compatible, hosted). Connectie via `libsql_experimental`. Migraties draaien handmatig via `_migrate()` in `app/database.py` (try/except rond ALTER TABLE).
- **Templates**: Jinja2 — gedeelde instantie in `app/templates_config.py` (bevat `from_json` filter voor extra_data JSON parsing in templates)
- **Scraper**: Playwright async browser automation (`app/scraper/`)
- **Foto's**: Cloudflare R2 via boto3 (`app/scraper/photos.py`)
- **Scheduler**: APScheduler BackgroundScheduler (`app/scheduler.py`)
- **Deploy**: Docker (`linux/amd64` target) op Railway

## Kritieke constraints

- **Turso stream expiry**: HTTP streams sluiten na ~70s idle. Foto-downloads zijn gecapped op 20/profiel/run. DB session recovery zit in `app/scheduler.py` (`_refresh_db_if_needed`).
- **AVIF**: Pillow kan `.avif` niet decoderen → fallback naar full-size URL als thumbnail.
- **`extra_data`**: JSON opgeslagen als TEXT in SQLite (niet JSONB). Filtering via ILIKE op de JSON-tekst.
- **Paginatie**: Gebruikt JS `goToPage()` + `URLSearchParams` omdat multi-select herhaalde URL params genereert die niet in Jinja2 `<a href>` links passen.
- **Advertentie scraping**: Ad-pagina's worden gescraped voor beschrijving, locatie en publicatiedatum. Alleen NIEUWE ad URLs (niet eerder in DB gezien) worden bezocht — bestaande ads worden overgeslagen. Logica in `app/scheduler.py` na `scrape_profile()`; `scrape_ad_page()` opent een nieuwe Playwright page per ad-URL.

## Lokaal draaien

```bash
docker compose up --build
```

App draait op `localhost:8000`.

## UI-architectuur

- **Layout**: Topnavbar (active link via `request.url.path`) + scraper-badge (groen pulserende dot via 15s polling)
- **Dashboard**: Links een vaste sidebar (filters altijd zichtbaar, 208px), rechts het profiel-grid/lijst
- **Filters**: Dynamische dropdowns — alleen waarden die effectief in DB bestaan. Provincie filter via `PROVINCE_CITIES` in `dashboard.py` (volledige Belgische gemeentelijst). Persistentie via localStorage + auto-redirect op kale `/`
- **Status**: Live voortgangsbalk (profiles_processed / profiles_found) via 5s polling op `/status/data`

## Bestandsstructuur

- `app/main.py` — FastAPI app, registreert routers
- `app/models.py` — SQLAlchemy models (Profile, Photo, Advertisement, ScrapeRun, ScraperSettings)
- `app/database.py` — Turso connectie, `init_db()`, handmatige migraties
- `app/routers/dashboard.py` — Overzicht, detail, archiveer endpoints; `PROVINCE_CITIES` mapping
- `app/routers/settings.py` — Scraper instellingen (interval, filters)
- `app/routers/status.py` — Scrape run status + `/status/data` JSON endpoint
- `app/scraper/` — Playwright scraper (profile.py, listing.py, browser.py, photos.py)
- `app/scheduler.py` — APScheduler + scrape loop met stream-recovery + auto-heractivatie gearchiveerde profielen
- `app/templates_config.py` — Gedeelde Jinja2 instantie met `from_json` filter
