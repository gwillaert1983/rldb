import asyncio
import logging
import re
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(timezone="UTC")

_stop_event = threading.Event()
_active_thread: threading.Thread | None = None


def start_scheduler():
    from app.models import ScraperSettings

    interval = settings.SCRAPE_INTERVAL_MINUTES
    try:
        db = SessionLocal()
        s = db.query(ScraperSettings).filter_by(id="settings").first()
        if s and s.scrape_interval_minutes:
            interval = s.scrape_interval_minutes
        db.close()
    except Exception:
        pass

    _scheduler.add_job(
        run_scrape_job,
        trigger=IntervalTrigger(minutes=interval),
        id="scrape_job",
        replace_existing=True,
        next_run_time=None,
    )
    _scheduler.start()
    logger.info("Scheduler gestart. Interval: %d minuten", interval)


def reschedule_interval(minutes: int):
    _scheduler.reschedule_job("scrape_job", trigger=IntervalTrigger(minutes=minutes))
    logger.info("Scrape interval aangepast naar %d minuten", minutes)


def shutdown_scheduler():
    _scheduler.shutdown(wait=False)


def scrape_is_running() -> bool:
    return _active_thread is not None and _active_thread.is_alive()


def start_scrape_thread() -> bool:
    """Start a scrape in a background thread. Returns False if already running."""
    global _active_thread
    if scrape_is_running():
        return False
    _stop_event.clear()
    _active_thread = threading.Thread(target=run_scrape_job, daemon=True)
    _active_thread.start()
    return True


def stop_scrape():
    """Signal the running scrape to stop after the current profile."""
    _stop_event.set()


def run_scrape_job():
    asyncio.run(_async_scrape_job())


def _passes_filter(extra: dict, s) -> bool:
    if s is None:
        return True

    def to_int(val):
        try:
            m = re.match(r"(\d+)", str(val).strip())
            return int(m.group(1)) if m else None
        except (ValueError, TypeError, AttributeError):
            return None

    age    = to_int(extra.get("age"))
    weight = to_int(extra.get("weight"))
    height = to_int(extra.get("height"))

    if age is not None:
        if s.min_age and age < s.min_age:
            return False
        if s.max_age and age > s.max_age:
            return False
    if weight is not None:
        if s.min_weight and weight < s.min_weight:
            return False
        if s.max_weight and weight > s.max_weight:
            return False
    if height is not None:
        if s.min_height and height < s.min_height:
            return False
        if s.max_height and height > s.max_height:
            return False

    if s.gender_filter:
        allowed = {g.strip() for g in s.gender_filter.split(",") if g.strip()}
        gender = str(extra.get("gender", "")).strip()
        if gender and gender not in allowed:
            return False

    return True


async def _async_scrape_job():
    from app.models import Advertisement, Profile, ScrapeRun, ScrapeStatus, ScraperSettings
    from app.scraper import upsert_profile
    from app.scraper.browser import managed_browser
    from app.scraper.listing import collect_profile_urls
    from app.scraper.profile import scrape_ad_page, scrape_profile

    db = SessionLocal()
    run = ScrapeRun(started_at=datetime.utcnow(), status=ScrapeStatus.running)
    db.add(run)
    db.commit()
    run_id = run.id

    logger.info("Scrape gestart (run id=%s)", run_id)

    def _refresh_db_if_needed(current_db, error: Exception):
        """Recreate the DB session when Turso stream has expired."""
        if "stream not found" not in str(error).lower() and "stream" not in str(error).lower():
            return current_db
        logger.warning("Turso stream verlopen — sessie opnieuw aanmaken")
        try:
            current_db.close()
        except Exception:
            pass
        new_db = SessionLocal()
        return new_db

    try:
        filter_settings = db.query(ScraperSettings).filter_by(id="settings").first()

        async with managed_browser() as context:
            urls = await collect_profile_urls(context)
            run.profiles_found = len(urls)
            db.commit()

            # Load archived profiles once — dict of source_url → phone
            archived_profiles: dict[str, str | None] = {
                row[0]: row[1]
                for row in db.query(Profile.source_url, Profile.phone).filter(Profile.is_archived == True).all()
            }

            for url in urls:
                if _stop_event.is_set():
                    logger.info("Scrape gestopt door gebruiker na %d profielen.", run.profiles_new or 0)
                    run.status = ScrapeStatus.stopped
                    break

                run.profiles_processed = (run.profiles_processed or 0) + 1

                if url in archived_profiles:
                    # Scrape to detect if a different person now uses this URL (different phone)
                    try:
                        data = await scrape_profile(context, url)
                        archived_phone = (archived_profiles[url] or "").strip()
                        current_phone = (data.phone or "").strip()
                        if current_phone and archived_phone and current_phone != archived_phone:
                            logger.info(
                                "Ander telefoonnummer (%s → %s), profiel heractiveren: %s",
                                archived_phone, current_phone, url,
                            )
                            if not _passes_filter(data.extra_data, filter_settings):
                                logger.info("Heractivering overgeslagen (filter): %s", url)
                            else:
                                is_new, is_changed = await upsert_profile(db, data, run)
                                reactivated = db.query(Profile).filter_by(source_url=url).first()
                                if reactivated:
                                    reactivated.is_archived = False
                                    db.commit()
                                if is_new:
                                    run.profiles_new = (run.profiles_new or 0) + 1
                                elif is_changed:
                                    run.profiles_updated = (run.profiles_updated or 0) + 1
                        else:
                            logger.info("Profiel gearchiveerd (zelfde tel.), overgeslagen: %s", url)
                    except Exception as e:
                        logger.warning("Heractivatiecheck mislukt voor %s: %s", url, e)
                        db = _refresh_db_if_needed(db, e)
                        if db is not None:
                            try:
                                run = db.query(ScrapeRun).filter_by(id=run_id).first()
                            except Exception:
                                pass
                    continue

                try:
                    data = await scrape_profile(context, url)
                    if not _passes_filter(data.extra_data, filter_settings):
                        logger.info("Profiel overgeslagen (filter): %s", url)
                        continue
                    # Scrape ad pages for new (unseen) ad URLs only
                    if data.ad_urls:
                        known_ad_urls = {
                            row[0]
                            for row in db.query(Advertisement.source_url)
                                .filter(Advertisement.source_url.in_(data.ad_urls))
                                .all()
                        }
                        for ad_url in data.ad_urls:
                            if ad_url not in known_ad_urls and ad_url not in data.ad_details:
                                try:
                                    data.ad_details[ad_url] = await scrape_ad_page(context, ad_url)
                                except Exception as ae:
                                    logger.warning("Ad page scrapen mislukt voor %s: %s", ad_url, ae)
                    is_new, is_changed = await upsert_profile(db, data, run)
                    if is_new:
                        run.profiles_new = (run.profiles_new or 0) + 1
                    elif is_changed:
                        run.profiles_updated = (run.profiles_updated or 0) + 1
                    db.commit()
                except Exception as e:
                    logger.warning("Profiel scrapen mislukt voor %s: %s", url, e)
                    db = _refresh_db_if_needed(db, e)
                    if db is not None:
                        try:
                            run = db.query(ScrapeRun).filter_by(id=run_id).first()
                        except Exception:
                            pass
                    continue

        if run.status == ScrapeStatus.running:
            run.status = ScrapeStatus.completed
        logger.info(
            "Scrape klaar: %d gevonden, %d nieuw, %d geüpdated, %d foto's",
            run.profiles_found, run.profiles_new or 0,
            run.profiles_updated or 0, run.photos_downloaded or 0,
        )
    except Exception as e:
        run.status = ScrapeStatus.failed
        run.error_message = str(e)
        logger.exception("Scrape job gefaald")
    finally:
        run.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        db.close()
