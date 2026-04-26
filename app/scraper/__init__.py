import json
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Advertisement, Photo, Profile, ScrapeRun
from app.scraper.photos import download_and_upload_photo
from app.scraper.profile import RawProfileData

logger = logging.getLogger(__name__)


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _parse_ad_url(url: str) -> tuple[str, str]:
    cats = ["prive-ontvangst", "escort", "massage", "shemale"]
    cat = next((c for c in cats if f"/{c}/" in url), "")
    slug = url.rstrip("/").rsplit("/", 1)[-1].replace(".html", "")
    title = re.sub(r"-(\d+)$", "", slug).replace("-", " ").title()
    return cat, title


async def upsert_profile(db: Session, data: RawProfileData, run: ScrapeRun) -> tuple[bool, bool]:
    profile = db.query(Profile).filter_by(source_url=data.source_url).first()
    now = datetime.utcnow()
    is_new = profile is None

    fingerprint = {
        "username": data.username,
        "display_name": data.display_name,
        "bio": data.bio,
        "phone": data.phone,
        "location": data.location,
        "price": data.price,
    }

    if is_new:
        profile = Profile(source_url=data.source_url, first_seen=now)
        db.add(profile)

    old_fingerprint = {
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "phone": profile.phone,
        "location": profile.location,
        "price": profile.price,
    }
    is_changed = fingerprint != old_fingerprint

    profile.username = data.username
    profile.display_name = data.display_name
    profile.bio = data.bio
    profile.phone = data.phone
    profile.location = data.location
    profile.price = data.price
    profile.extra_data = json.dumps(data.extra_data, ensure_ascii=False)
    profile.last_scraped = now
    if is_changed:
        profile.last_changed = now

    db.flush()

    existing_urls = {p.source_url for p in profile.photos}
    # Limit new downloads per run to prevent long-running sessions that cause Turso stream expiry
    new_photo_urls = [u for u in data.photo_urls if u not in existing_urls][:20]

    for position, url in enumerate(new_photo_urls):
        try:
            photo_data = await download_and_upload_photo(url, profile.id, position)
            photo = Photo(
                profile_id=profile.id,
                source_url=url,
                position=len(existing_urls) + position,
                **photo_data,
            )
            db.add(photo)
            run.photos_downloaded = (run.photos_downloaded or 0) + 1
        except Exception as e:
            logger.warning("Foto downloaden mislukt voor %s: %s", url, e)

    # Upsert advertisements
    seen_ad_urls: set[str] = set()
    for ad_url in (data.ad_urls or []):
        seen_ad_urls.add(ad_url)
        cat, title = _parse_ad_url(ad_url)
        ad = db.query(Advertisement).filter_by(source_url=ad_url).first()
        if ad:
            ad.last_seen = now
            ad.is_active = True
        else:
            detail = data.ad_details.get(ad_url, {})
            ad_location = detail.get("location") or data.location
            ad_desc = detail.get("description") or None
            ad_pub = _parse_date(detail.get("published_at_str", ""))
            db.add(Advertisement(
                profile_id=profile.id,
                source_url=ad_url,
                category=cat,
                title=title,
                location=ad_location,
                description=ad_desc,
                published_at=ad_pub,
                first_seen=now,
                last_seen=now,
            ))

    if seen_ad_urls:
        db.query(Advertisement).filter(
            Advertisement.profile_id == profile.id,
            Advertisement.source_url.notin_(seen_ad_urls),
        ).update({"is_active": False}, synchronize_session=False)

    db.commit()
    return is_new, is_changed
