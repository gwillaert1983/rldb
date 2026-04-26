from typing import List

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, require_login
from app.models import Photo, Profile, ScraperSettings, ScrapeRun
from app.storage import wipe_bucket
from app.templates_config import templates

router = APIRouter()


def _opt_int(val: str) -> int | None:
    try:
        v = int(val.strip())
        return v if v > 0 else None
    except (ValueError, AttributeError):
        return None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
    saved: int = 0,
    wiped: int = 0,
):
    if isinstance(user, RedirectResponse):
        return user

    s = db.query(ScraperSettings).filter_by(id="settings").first()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "s": s,
            "saved": saved,
            "wiped": wiped,
            "env_interval": settings.SCRAPE_INTERVAL_MINUTES,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
    min_age: str = Form(""),
    max_age: str = Form(""),
    min_weight: str = Form(""),
    max_weight: str = Form(""),
    min_height: str = Form(""),
    max_height: str = Form(""),
    genders: List[str] = Form([]),
    scrape_interval: str = Form(""),
):
    if isinstance(user, RedirectResponse):
        return user

    s = db.query(ScraperSettings).filter_by(id="settings").first()
    if not s:
        s = ScraperSettings(id="settings")
        db.add(s)

    s.min_age       = _opt_int(min_age)
    s.max_age       = _opt_int(max_age)
    s.min_weight    = _opt_int(min_weight)
    s.max_weight    = _opt_int(max_weight)
    s.min_height    = _opt_int(min_height)
    s.max_height    = _opt_int(max_height)
    s.gender_filter = ",".join(genders) if genders else None

    new_interval = _opt_int(scrape_interval)
    s.scrape_interval_minutes = new_interval
    db.commit()

    if new_interval:
        try:
            from app.scheduler import reschedule_interval
            reschedule_interval(new_interval)
        except Exception:
            pass

    return RedirectResponse("/settings?saved=1", status_code=303)


@router.get("/settings/reset")
async def settings_reset(
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    s = db.query(ScraperSettings).filter_by(id="settings").first()
    if s:
        s.min_age = s.max_age = s.min_weight = s.max_weight = s.min_height = s.max_height = None
        s.gender_filter = None
        s.scrape_interval_minutes = None
        db.commit()

    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/wipe")
async def settings_wipe(
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    wipe_bucket()
    db.query(Photo).delete()
    db.query(Profile).delete()
    db.query(ScrapeRun).delete()
    db.commit()

    return RedirectResponse("/settings?wiped=1", status_code=303)
