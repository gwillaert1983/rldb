import math
from typing import List

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, require_login
from app.models import Photo, Profile, ScrapeRun, ScrapeStatus, ScraperSettings
from app.storage import wipe_bucket
from app.templates_config import templates

router = APIRouter()


def _opt_int(val: str) -> int | None:
    try:
        v = int(val.strip())
        return v if v > 0 else None
    except (ValueError, AttributeError):
        return None


def _compute_scrape_stats(db: Session, current_interval: int) -> dict | None:
    recent = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.status == ScrapeStatus.completed, ScrapeRun.finished_at.isnot(None))
        .order_by(ScrapeRun.started_at.desc())
        .limit(30)
        .all()
    )
    if not recent:
        return None

    durations = [(r.finished_at - r.started_at).total_seconds() / 60 for r in recent]
    avg_dur = sum(durations) / len(durations)
    total_found   = sum(r.profiles_found   or 0 for r in recent)
    total_skipped = sum(r.profiles_skipped or 0 for r in recent)
    total_new     = sum(r.profiles_new     or 0 for r in recent)
    skip_rate = round(total_skipped / total_found * 100) if total_found else 0
    new_rate  = round(total_new     / total_found * 100) if total_found else 0

    tips = []
    if avg_dur > current_interval * 0.85:
        min_safe = math.ceil(avg_dur * 1.25)
        tips.append({"type": "warning",
                     "text": (f"Runs duren gemiddeld {avg_dur:.0f} min — dicht bij je interval van "
                              f"{current_interval} min. Verhoog naar minstens {min_safe} min om "
                              f"overlapping te vermijden.")})
    if skip_rate > 55:
        tips.append({"type": "info",
                     "text": (f"{skip_rate}% van de gevonden profielen wordt overgeslagen door je "
                              f"filters. Overweeg de filters te verruimen of het interval te verhogen.")})
    if new_rate < 4 and skip_rate < 40:
        suggested = min(math.ceil(avg_dur * 3), 120)
        tips.append({"type": "info",
                     "text": (f"Slechts {new_rate}% nieuwe profielen per run. "
                              f"Je kunt het interval veilig verhogen naar ≈{suggested} min.")})
    if not tips:
        tips.append({"type": "ok",
                     "text": "De instellingen zien er goed uit op basis van de recente runs."})

    return {
        "sample": len(recent),
        "avg_dur": round(avg_dur, 1),
        "avg_found": round(total_found / len(recent), 1),
        "skip_rate": skip_rate,
        "new_rate": new_rate,
        "tips": tips,
    }


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
    current_interval = (s.scrape_interval_minutes if s and s.scrape_interval_minutes
                        else settings.SCRAPE_INTERVAL_MINUTES)
    scrape_stats = _compute_scrape_stats(db, current_interval)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "s": s,
            "saved": saved,
            "wiped": wiped,
            "env_interval": settings.SCRAPE_INTERVAL_MINUTES,
            "scrape_stats": scrape_stats,
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
