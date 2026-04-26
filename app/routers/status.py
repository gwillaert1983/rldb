from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_login
from app.models import Photo, Profile, ScrapeRun
from app.templates_config import templates


def _fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    return f"{b / 1024 ** 3:.2f} GB"

router = APIRouter()


@router.get("/status", response_class=HTMLResponse)
async def status_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import scrape_is_running

    total_profiles = db.query(Profile).count()
    total_photos = db.query(Photo).count()
    storage_bytes = db.query(func.sum(Photo.file_size_bytes)).scalar() or 0
    last_run = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).first()
    recent_runs = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(20).all()

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "total_profiles": total_profiles,
            "total_photos": total_photos,
            "storage_bytes": storage_bytes,
            "storage_fmt": _fmt_bytes(storage_bytes),
            "last_run": last_run,
            "recent_runs": recent_runs,
            "is_running": scrape_is_running(),
        },
    )


@router.get("/status/data", response_class=JSONResponse)
async def status_data(
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    from app.scheduler import scrape_is_running

    total_profiles = db.query(Profile).count()
    total_photos = db.query(Photo).count()
    storage_bytes = db.query(func.sum(Photo.file_size_bytes)).scalar() or 0
    recent_runs = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(20).all()
    last_run = recent_runs[0] if recent_runs else None

    def fmt_run(r):
        duration = None
        if r.finished_at and r.started_at:
            secs = int((r.finished_at - r.started_at).total_seconds())
            duration = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
        return {
            "id": r.id,
            "status": r.status.value,
            "started_at": r.started_at.strftime("%d/%m/%Y %H:%M"),
            "duration": duration,
            "profiles_found": r.profiles_found or 0,
            "profiles_processed": r.profiles_processed or 0,
            "profiles_new": r.profiles_new or 0,
            "profiles_updated": r.profiles_updated or 0,
            "photos_downloaded": r.photos_downloaded or 0,
            "error_message": r.error_message,
        }

    return JSONResponse({
        "is_running": scrape_is_running(),
        "total_profiles": total_profiles,
        "total_photos": total_photos,
        "storage_fmt": _fmt_bytes(storage_bytes),
        "runs_count": len(recent_runs),
        "last_run": fmt_run(last_run) if last_run else None,
        "recent_runs": [fmt_run(r) for r in recent_runs],
    })


@router.post("/scrape/start")
async def start_scrape_now(user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    from app.scheduler import start_scrape_thread
    started = start_scrape_thread()
    return JSONResponse({"status": "started" if started else "already_running"})


@router.post("/scrape/stop")
async def stop_scrape_now(user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    from app.scheduler import stop_scrape
    stop_scrape()
    return JSONResponse({"status": "stop_requested"})
