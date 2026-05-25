import json
import logging
from datetime import datetime, timedelta

import pytz
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.dependencies import get_db, require_login
from app.geo import all_city_options
from app.models import SavedSearch, ScrapeRun, ScrapeStatus
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter()

CATEGORIES = [
    {"slug": "prive-ontvangst", "label": "Privé-ontvangst"},
    {"slug": "escort",          "label": "Escort"},
    {"slug": "massage",         "label": "Massage"},
]

INTERVAL_OPTIONS = [
    {"hours": 6,   "label": "Elke 6 uur"},
    {"hours": 12,  "label": "Elke 12 uur"},
    {"hours": 24,  "label": "Dagelijks"},
    {"hours": 48,  "label": "Om de 2 dagen"},
    {"hours": 72,  "label": "Om de 3 dagen"},
    {"hours": 168, "label": "Wekelijks"},
]


def _utc_to_local(dt) -> str | None:
    if dt is None:
        return None
    tz = pytz.timezone("Europe/Brussels")
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def _next_run(ss: SavedSearch) -> str | None:
    if not ss.is_active:
        return None
    if ss.last_run_at is None:
        return "Nu gepland"
    next_dt = ss.last_run_at + timedelta(hours=ss.schedule_interval_hours or 24)
    return _utc_to_local(next_dt)


def _fmt_saved_search(ss: SavedSearch) -> dict:
    cats = []
    if ss.categories:
        try:
            cats = json.loads(ss.categories)
        except Exception:
            pass
    return {
        "id": ss.id,
        "name": ss.name,
        "center_city": ss.center_city,
        "center_city_name": ss.center_city.replace("-", " ").title(),
        "radius_km": ss.radius_km or 50,
        "categories": cats,
        "age_min": ss.age_min,
        "age_max": ss.age_max,
        "schedule_interval_hours": ss.schedule_interval_hours or 24,
        "max_pages_per_city": ss.max_pages_per_city or 5,
        "is_active": bool(ss.is_active),
        "last_run_at": _utc_to_local(ss.last_run_at),
        "next_run_at": _next_run(ss),
        "created_at": _utc_to_local(ss.created_at),
    }


def _fmt_run(r: ScrapeRun) -> dict:
    duration = None
    if r.finished_at and r.started_at:
        secs = int((r.finished_at - r.started_at).total_seconds())
        duration = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
    cfg = {}
    if r.search_config:
        try:
            cfg = json.loads(r.search_config)
        except Exception:
            pass
    return {
        "id": r.id,
        "status": r.status.value,
        "started_at": _utc_to_local(r.started_at),
        "finished_at": _utc_to_local(r.finished_at),
        "duration": duration,
        "profiles_found": r.profiles_found or 0,
        "profiles_processed": r.profiles_processed or 0,
        "profiles_new": r.profiles_new or 0,
        "profiles_updated": r.profiles_updated or 0,
        "profiles_skipped": r.profiles_skipped or 0,
        "error_message": r.error_message,
        "city_urls": cfg.get("city_urls", []),
        "categories": cfg.get("categories", []),
        "age_min": cfg.get("age_min"),
        "age_max": cfg.get("age_max"),
        "saved_search_id": r.saved_search_id,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/zoeken", response_class=HTMLResponse)
async def search_page(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import get_active_thread_type, scrape_is_running

    saved_searches = (
        db.query(SavedSearch).order_by(SavedSearch.created_at.desc()).all()
    )
    recent_runs = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.run_type == "search")
        .order_by(ScrapeRun.started_at.desc())
        .limit(30)
        .all()
    )

    # Build a name map: saved_search_id → name
    ss_names = {ss.id: ss.name for ss in saved_searches}

    runs_fmt = _fmt_run_list(recent_runs, ss_names)

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "saved_searches": [_fmt_saved_search(ss) for ss in saved_searches],
            "recent_runs": runs_fmt,
            "categories": CATEGORIES,
            "interval_options": INTERVAL_OPTIONS,
            "city_options": all_city_options(),
            "is_running": scrape_is_running(),
            "is_search_running": scrape_is_running() and get_active_thread_type() == "search",
        },
    )


def _fmt_run_list(runs, ss_names: dict) -> list[dict]:
    result = []
    for r in runs:
        d = _fmt_run(r)
        d["saved_search_name"] = ss_names.get(r.saved_search_id, "")
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Saved search CRUD
# ---------------------------------------------------------------------------

@router.post("/zoeken/opslaan")
async def create_saved_search(
    request: Request,
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    form = await request.form()
    name        = (form.get("name") or "").strip()
    center_city = (form.get("center_city") or "").strip()
    if not name or not center_city:
        return JSONResponse({"status": "error", "message": "Naam en centrumstad zijn verplicht"}, status_code=400)

    try:
        radius_km  = int(form.get("radius_km") or 50)
        age_min    = int(form.get("age_min")) if form.get("age_min") else None
        age_max    = int(form.get("age_max")) if form.get("age_max") else None
        interval   = int(form.get("schedule_interval_hours") or 24)
        max_pages  = int(form.get("max_pages_per_city") or 5)
    except (ValueError, TypeError):
        return JSONResponse({"status": "error", "message": "Ongeldige numerieke waarden"}, status_code=400)

    categories = form.getlist("categories")

    # Validate center city exists in geo data
    from app.geo import get_city_coords
    if get_city_coords(center_city) is None:
        return JSONResponse({"status": "error", "message": f"Onbekende stad: {center_city}"}, status_code=400)

    ss = SavedSearch(
        name=name,
        center_city=center_city,
        radius_km=radius_km,
        categories=json.dumps(categories),
        age_min=age_min,
        age_max=age_max,
        schedule_interval_hours=interval,
        max_pages_per_city=max_pages,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(ss)
    db.commit()
    return JSONResponse({"status": "ok", "id": ss.id})


@router.delete("/zoeken/{search_id}")
async def delete_saved_search(
    search_id: str,
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user
    ss = db.query(SavedSearch).filter_by(id=search_id).first()
    if not ss:
        return JSONResponse({"status": "not_found"}, status_code=404)
    db.delete(ss)
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/zoeken/{search_id}/toggle")
async def toggle_saved_search(
    search_id: str,
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user
    ss = db.query(SavedSearch).filter_by(id=search_id).first()
    if not ss:
        return JSONResponse({"status": "not_found"}, status_code=404)
    ss.is_active = not ss.is_active
    db.commit()
    return JSONResponse({"status": "ok", "is_active": ss.is_active})


@router.post("/zoeken/{search_id}/start")
async def run_saved_search_now(
    search_id: str,
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import scrape_is_running, start_search_thread

    if scrape_is_running():
        return JSONResponse({"status": "already_running"})

    ss = db.query(SavedSearch).filter_by(id=search_id).first()
    if not ss:
        return JSONResponse({"status": "not_found"}, status_code=404)

    cats = []
    if ss.categories:
        try:
            cats = json.loads(ss.categories)
        except Exception:
            pass

    started = start_search_thread(
        city_urls=[],
        categories=cats,
        max_pages=ss.max_pages_per_city or 5,
        age_min=ss.age_min,
        age_max=ss.age_max,
        saved_search_id=ss.id,
        search_query=ss.center_city,
    )
    return JSONResponse({"status": "started" if started else "already_running"})


# ---------------------------------------------------------------------------
# Manual one-off search (still supported)
# ---------------------------------------------------------------------------

@router.post("/zoeken/start")
async def start_manual_search(
    request: Request,
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import scrape_is_running, start_search_thread

    if scrape_is_running():
        return JSONResponse({"status": "already_running"})

    form = await request.form()
    city_urls  = form.getlist("city_urls")
    categories = form.getlist("categories")
    try:
        max_pages = int(form.get("max_pages", 5))
        max_pages = max(1, min(max_pages, 50))
    except (ValueError, TypeError):
        max_pages = 5

    if not city_urls:
        return JSONResponse({"status": "error", "message": "Geen steden geselecteerd"}, status_code=400)

    started = start_search_thread(city_urls, categories or [], max_pages)
    return JSONResponse({"status": "started" if started else "already_running"})


# ---------------------------------------------------------------------------
# Status & utility
# ---------------------------------------------------------------------------

@router.get("/zoeken/steden/{province_slug}", response_class=JSONResponse)
async def get_cities(
    province_slug: str,
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scraper.search import get_province_city_urls

    city_urls = await get_province_city_urls(province_slug)
    cities = []
    for url in city_urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")
        name = slug.replace("-", " ").title()
        cities.append({"slug": slug, "name": name, "url": url})

    return JSONResponse(cities)


@router.get("/zoeken/status", response_class=JSONResponse)
async def search_status(
    db=Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import get_active_thread_type, scrape_is_running

    last_run = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.run_type == "search")
        .order_by(ScrapeRun.started_at.desc())
        .first()
    )

    return JSONResponse({
        "is_running": scrape_is_running() and get_active_thread_type() == "search",
        "last_run": _fmt_run(last_run) if last_run else None,
    })


@router.post("/zoeken/stop")
async def stop_search(user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    from app.scheduler import stop_scrape
    stop_scrape()
    return JSONResponse({"status": "stop_requested"})
