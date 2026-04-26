import hashlib
import logging
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.storage import upload_bytes

logger = logging.getLogger(__name__)

THUMB_SIZE = (400, 400)

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


async def download_and_upload_photo(url: str, profile_id: str, position: int) -> dict:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    ext = _guess_ext(content_type, url)
    sha = hashlib.sha256(url.encode()).hexdigest()[:20]

    key = f"photos/{profile_id}/{sha}{ext}"
    thumb_key = f"photos/{profile_id}/thumbs/{sha}{ext}"

    r2_url = upload_bytes(resp.content, key, content_type)

    try:
        img = Image.open(BytesIO(resp.content))
        w, h = img.size
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        buf = BytesIO()
        img_format = "JPEG" if ext in (".jpg", ".jpeg") else ext.lstrip(".").upper()
        img.save(buf, format=img_format)
        thumb_r2_url = upload_bytes(buf.getvalue(), thumb_key, content_type)
    except Exception as e:
        logger.warning("Thumbnail aanmaken mislukt: %s", e)
        w, h = 0, 0
        thumb_key = key
        thumb_r2_url = r2_url

    return {
        "r2_key": key,
        "r2_url": r2_url,
        "thumbnail_r2_key": thumb_key,
        "thumbnail_r2_url": thumb_r2_url,
        "width": w,
        "height": h,
        "file_size_bytes": len(resp.content),
    }


def _guess_ext(content_type: str, url: str) -> str:
    for mime, ext in MIME_TO_EXT.items():
        if mime in content_type:
            return ext
    suffix = Path(url.split("?")[0]).suffix.lower()
    return suffix if suffix in MIME_TO_EXT.values() else ".jpg"
