import asyncio
import json as _json
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
_active_thread_type: str = "full"  # "full" or "search"


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
        _scheduled_scrape_job,
        trigger=IntervalTrigger(minutes=interval),
        id="scrape_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_saved_searches_job,
        trigger=IntervalTrigger(minutes=30),
        id="saved_search_job",
        replace_existing=True,
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
    global _active_thread, _active_thread_type
    if scrape_is_running():
        return False
    _stop_event.clear()
    _active_thread_type = "full"
    _active_thread = threading.Thread(target=run_scrape_job, daemon=True)
    _active_thread.start()
    return True


def start_search_thread(
    city_urls: list[str],
    categories: list[str],
    max_pages: int = 5,
    age_min: int | None = None,
    age_max: int | None = None,
    saved_search_id: str | None = None,
    search_query: str | None = None,
) -> bool:
    """Start a targeted city/category search in a background thread. Returns False if already running."""
    global _active_thread, _active_thread_type
    if scrape_is_running():
        return False
    _stop_event.clear()
    _active_thread_type = "search"
    _active_thread = threading.Thread(
        target=lambda: run_search_job(city_urls, categories, max_pages, age_min, age_max, saved_search_id, search_query),
        daemon=True,
    )
    _active_thread.start()
    return True


def get_active_thread_type() -> str:
    return _active_thread_type


def stop_scrape():
    """Signal the running scrape or search to stop after the current profile."""
    _stop_event.set()


def get_next_run_time() -> str | None:
    import pytz
    job = _scheduler.get_job("scrape_job")
    if job is None or job.next_run_time is None:
        return None
    tz = pytz.timezone("Europe/Brussels")
    return job.next_run_time.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def run_scrape_job():
    asyncio.run(_async_scrape_job())


def run_search_job(
    city_urls: list[str],
    categories: list[str],
    max_pages: int = 5,
    age_min: int | None = None,
    age_max: int | None = None,
    saved_search_id: str | None = None,
    search_query: str | None = None,
):
    asyncio.run(_async_search_job(city_urls, categories, max_pages, age_min, age_max, saved_search_id, search_query))


def _scheduled_scrape_job():
    """APScheduler entry-point — skips the run if the current time window is disabled."""
    import pytz
    from app.models import ScraperSettings
    tz = pytz.timezone("Europe/Brussels")
    hour = datetime.now(tz).hour
    slot = hour // 6  # 0=0-6, 1=6-12, 2=12-18, 3=18-24
    try:
        db = SessionLocal()
        s = db.query(ScraperSettings).filter_by(id="settings").first()
        windows = [
            int(getattr(s, "window_0_6",  1) or 1) if s else 1,
            int(getattr(s, "window_6_12",  1) or 1) if s else 1,
            int(getattr(s, "window_12_18", 1) or 1) if s else 1,
            int(getattr(s, "window_18_24", 1) or 1) if s else 1,
        ]
        db.close()
    except Exception:
        windows = [1, 1, 1, 1]
    if not windows[slot]:
        logger.info("Scrape overgeslagen: venster %d:00–%d:00 uitgeschakeld", slot * 6, (slot + 1) * 6)
        return
    run_scrape_job()


def _to_int(val):
    try:
        m = re.match(r"(\d+)", str(val).strip())
        return int(m.group(1)) if m else None
    except (ValueError, TypeError, AttributeError):
        return None


def _matches_group(extra: dict, g: dict) -> bool:
    age    = _to_int(extra.get("age"))
    weight = _to_int(extra.get("weight"))
    height = _to_int(extra.get("height"))

    if g.get("age_min")    and age    is not None and age    < g["age_min"]:    return False
    if g.get("age_max")    and age    is not None and age    > g["age_max"]:    return False
    if g.get("weight_max") and weight is not None and weight > g["weight_max"]: return False
    if g.get("height_max") and height is not None and height > g["height_max"]: return False

    genders = g.get("genders") or []
    if genders and str(extra.get("gender", "")).strip() not in genders:
        return False

    nationalities = g.get("nationalities") or []
    if nationalities and str(extra.get("nationality", "")).strip() not in nationalities:
        return False

    languages = g.get("languages") or []
    if languages:
        raw_langs = extra.get("languages", "")
        if isinstance(raw_langs, list):
            flat_langs = {l.strip() for l in raw_langs if l.strip()}
        elif isinstance(raw_langs, str):
            flat_langs = {l.strip() for l in raw_langs.split(",") if l.strip()}
        else:
            flat_langs = set()
        if not any(lang in flat_langs for lang in languages):
            return False

    services = g.get("services") or []
    if services:
        raw_svcs = extra.get("services", {})
        flat = set()
        if isinstance(raw_svcs, dict):
            for items in raw_svcs.values():
                if isinstance(items, list):
                    flat.update(i.strip() for i in items if i.strip())
        if not any(svc in flat for svc in services):
            return False

    return True


def _passes_filter(extra: dict, s) -> bool:
    if s is None:
        return True

    groups_json = getattr(s, "filter_groups", None)
    if groups_json:
        try:
            groups = _json.loads(groups_json)
        except Exception:
            groups = []
        if groups:
            return any(_matches_group(extra, g) for g in groups)
        return True  # lege lijst = geen filter

    # Fallback: oude individuele velden (AND-logica)
    age    = _to_int(extra.get("age"))
    weight = _to_int(extra.get("weight"))
    height = _to_int(extra.get("height"))

    if age is not None:
        if s.min_age and age < s.min_age:   return False
        if s.max_age and age > s.max_age:   return False
    if weight is not None:
        if s.min_weight and weight < s.min_weight: return False
        if s.max_weight and weight > s.max_weight: return False
    if height is not None:
        if s.min_height and height < s.min_height: return False
        if s.max_height and height > s.max_height: return False

    if s.gender_filter:
        allowed = {g.strip() for g in s.gender_filter.split(",") if g.strip()}
        if allowed and str(extra.get("gender", "")).strip() not in allowed:
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
                                run.profiles_skipped = (run.profiles_skipped or 0) + 1
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
                            run.profiles_skipped = (run.profiles_skipped or 0) + 1
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
                        run.profiles_skipped = (run.profiles_skipped or 0) + 1
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


def _check_saved_searches_job():
    """Every 30 min: run the highest-priority due saved search (oldest last_run_at)."""
    from datetime import timedelta
    from app.models import SavedSearch

    if scrape_is_running():
        return

    db = SessionLocal()
    try:
        searches = (
            db.query(SavedSearch)
            .filter_by(is_active=True)
            .order_by(SavedSearch.last_run_at.asc())
            .all()
        )
        now = datetime.utcnow()
        for s in searches:
            due = (
                s.last_run_at is None
                or (now - s.last_run_at) >= timedelta(hours=s.schedule_interval_hours or 24)
            )
            if not due:
                continue
            cats = _json.loads(s.categories or "[]")
            started = start_search_thread(
                city_urls=[],
                categories=cats,
                max_pages=s.max_pages_per_city or 5,
                age_min=s.age_min,
                age_max=s.age_max,
                saved_search_id=s.id,
                search_query=s.center_city,
            )
            if started:
                logger.info("Automatische zoekrun gestart voor saved search '%s'", s.name)
            break  # één run per scheduler-tick
    except Exception as e:
        logger.exception("Fout in _check_saved_searches_job: %s", e)
    finally:
        db.close()


async def _async_search_job(
    city_urls: list[str],
    categories: list[str],
    max_pages: int,
    age_min: int | None = None,
    age_max: int | None = None,
    saved_search_id: str | None = None,
    search_query: str | None = None,
):
    from app.models import Advertisement, SavedSearch, ScrapeRun, ScrapeStatus
    from app.scraper import upsert_profile
    from app.scraper.browser import managed_browser
    from app.scraper.profile import scrape_ad_page, scrape_profile
    from app.scraper.search import collect_ad_urls_from_listing, collect_ad_urls_from_search
    from app.scraper import _parse_date

    db = SessionLocal()
    run = ScrapeRun(
        started_at=datetime.utcnow(),
        status=ScrapeStatus.running,
        run_type="search",
        search_config=_json.dumps({
            "city_urls": city_urls,
            "categories": categories,
            "max_pages": max_pages,
            "age_min": age_min,
            "age_max": age_max,
        }),
        saved_search_id=saved_search_id,
    )
    db.add(run)
    db.commit()
    run_id = run.id
    logger.info(
        "Zoekrun gestart (id=%s) voor %d steden, categorieën: %s, leeftijd: %s–%s",
        run_id, len(city_urls), categories, age_min, age_max,
    )

    def _refresh_db(current_db, error: Exception):
        if "stream not found" not in str(error).lower() and "stream" not in str(error).lower():
            return current_db
        logger.warning("Turso stream verlopen — sessie opnieuw aanmaken")
        try:
            current_db.close()
        except Exception:
            pass
        return SessionLocal()

    try:
        async with managed_browser() as context:
            # 1. Collect ad URLs — via site search (saved searches) or city listing pages (manual)
            all_ad_urls: list[str] = []
            if search_query:
                all_ad_urls = await collect_ad_urls_from_search(
                    context, search_query, categories=categories or None
                )
            else:
                for city_url in city_urls:
                    if _stop_event.is_set():
                        break
                    try:
                        found = await collect_ad_urls_from_listing(
                            context, city_url, categories=categories or None, max_pages=max_pages
                        )
                        all_ad_urls.extend(found)
                        logger.info("  %d advertentie-URLs gevonden op %s", len(found), city_url)
                    except Exception as e:
                        logger.warning("Fout bij verzamelen ads van %s: %s", city_url, e)
                all_ad_urls = list(dict.fromkeys(all_ad_urls))

            run.profiles_found = len(all_ad_urls)
            db.commit()
            logger.info("Totaal %d unieke advertentie-URLs gevonden", len(all_ad_urls))

            # 2. Process each ad URL
            for ad_url in all_ad_urls:
                if _stop_event.is_set():
                    run.status = ScrapeStatus.stopped
                    logger.info("Zoekrun gestopt door gebruiker")
                    break

                run.profiles_processed = (run.profiles_processed or 0) + 1

                try:
                    # Scrape ad page — gives us profile_url + published_at for dedup
                    ad_data = await scrape_ad_page(context, ad_url)
                    profile_url = ad_data.get("profile_url", "")
                    if not profile_url:
                        logger.debug("Geen profiel-URL op %s — overgeslagen", ad_url)
                        run.profiles_skipped = (run.profiles_skipped or 0) + 1
                        continue

                    # Smart dedup: skip if ad exists with same published_at (not renewed)
                    new_pub = _parse_date(ad_data.get("published_at_str", ""))
                    try:
                        existing_ad = db.query(Advertisement).filter_by(source_url=ad_url).first()
                        if existing_ad:
                            if new_pub and existing_ad.published_at:
                                if new_pub.date() == existing_ad.published_at.date():
                                    run.profiles_skipped = (run.profiles_skipped or 0) + 1
                                    continue
                            elif existing_ad.published_at is None and new_pub is None:
                                age_h = (datetime.utcnow() - existing_ad.last_seen).total_seconds() / 3600
                                if age_h < 6:
                                    run.profiles_skipped = (run.profiles_skipped or 0) + 1
                                    continue
                    except Exception as e:
                        db = _refresh_db(db, e)
                        try:
                            run = db.query(ScrapeRun).filter_by(id=run_id).first()
                        except Exception:
                            pass
                        continue

                    # Scrape full profile
                    data = await scrape_profile(context, profile_url)

                    # Age filter
                    if age_min is not None or age_max is not None:
                        age_val = _to_int((data.extra_data or {}).get("age"))
                        if age_val is not None:
                            if age_min is not None and age_val < age_min:
                                run.profiles_skipped = (run.profiles_skipped or 0) + 1
                                continue
                            if age_max is not None and age_val > age_max:
                                run.profiles_skipped = (run.profiles_skipped or 0) + 1
                                continue

                    # Ensure the trigger ad is linked to this profile
                    if ad_url not in data.ad_urls:
                        data.ad_urls.append(ad_url)
                    if ad_url not in data.ad_details:
                        data.ad_details[ad_url] = ad_data

                    # Scrape other new ad pages on this profile
                    if data.ad_urls:
                        known_ad_urls = {
                            row[0]
                            for row in db.query(Advertisement.source_url)
                                .filter(Advertisement.source_url.in_(data.ad_urls))
                                .all()
                        }
                        for other_url in data.ad_urls:
                            if other_url != ad_url and other_url not in known_ad_urls and other_url not in data.ad_details:
                                try:
                                    data.ad_details[other_url] = await scrape_ad_page(context, other_url)
                                except Exception as ae:
                                    logger.warning("Bijkomende ad scrapen mislukt %s: %s", other_url, ae)

                    is_new, is_changed = await upsert_profile(db, data, run)
                    if is_new:
                        run.profiles_new = (run.profiles_new or 0) + 1
                    elif is_changed:
                        run.profiles_updated = (run.profiles_updated or 0) + 1
                    db.commit()

                except Exception as e:
                    logger.warning("Fout bij verwerken %s: %s", ad_url, e)
                    db = _refresh_db(db, e)
                    if db is not None:
                        try:
                            run = db.query(ScrapeRun).filter_by(id=run_id).first()
                        except Exception:
                            pass
                    continue

        if run.status == ScrapeStatus.running:
            run.status = ScrapeStatus.completed
        logger.info(
            "Zoekrun klaar: %d ads gevonden, %d nieuw, %d geüpdated, %d overgeslagen",
            run.profiles_found, run.profiles_new or 0,
            run.profiles_updated or 0, run.profiles_skipped or 0,
        )

        # Update last_run_at on the SavedSearch
        if saved_search_id:
            try:
                ss = db.query(SavedSearch).filter_by(id=saved_search_id).first()
                if ss:
                    ss.last_run_at = datetime.utcnow()
                    db.commit()
            except Exception as e:
                logger.warning("last_run_at update mislukt: %s", e)

    except Exception as e:
        run.status = ScrapeStatus.failed
        run.error_message = str(e)
        logger.exception("Zoekrun gefaald")
    finally:
        run.finished_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
        db.close()
