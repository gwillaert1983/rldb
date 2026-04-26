import logging

from playwright.async_api import BrowserContext

from app.config import settings
from app.scraper.browser import handle_age_gate, make_absolute

logger = logging.getLogger(__name__)

BASE = "https://www.redlights.be"


async def collect_profile_urls(context: BrowserContext) -> list[str]:
    page = await context.new_page()
    urls: list[str] = []
    page_num = 1

    # Navigate with ?adult=1 on first page to bypass age gate cookie
    current_url = f"{settings.TARGET_BASE_URL.rstrip('/')}/?adult=1"

    max_pages = settings.SCRAPE_MAX_PAGES
    while current_url:
        if max_pages and page_num > max_pages:
            logger.info("Pagina-limiet bereikt (%d pagina's).", max_pages)
            break
        logger.info("Pagina %d ophalen: %s", page_num, current_url)
        try:
            await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.error("Fout bij ophalen pagina %s: %s", current_url, e)
            break

        # Handle age gate if it appears (fallback for subsequent pages)
        if page_num == 1:
            await handle_age_gate(page)

        # Collect all profile links — filter to only slugged profiles
        links = await page.locator("a[href*='/profiel/']").all()
        found = 0
        for link in links:
            href = await link.get_attribute("href")
            if href and _is_profile_url(href):
                full = make_absolute(href, BASE)
                urls.append(full)
                found += 1

        logger.info("  %d profielen gevonden op pagina %d", found, page_num)

        # Pagination: look for a link to next page number
        next_url = await _find_next_page(page, page_num)
        current_url = next_url
        page_num += 1

    await page.close()
    deduped = list(dict.fromkeys(urls))
    logger.info("Totaal unieke profiel-URLs gevonden: %d", len(deduped))
    return deduped


def _is_profile_url(href: str) -> bool:
    """True only for /profiel/[slug]/ links, not /profiel/ or /profiel/?page=N."""
    path = href.split("?")[0].rstrip("/")
    parts = [p for p in path.split("/") if p]
    # Expect ["profiel", "<slug>"] — exactly two parts ending in profiel/slug
    return (
        len(parts) >= 2
        and parts[-2] == "profiel"
        and parts[-1] != "profiel"
    )


async def _find_next_page(page, current_page: int) -> str | None:
    next_page = current_page + 1
    # Try direct page link
    try:
        link = page.locator(f"a[href*='page={next_page}']").first
        if await link.is_visible(timeout=2000):
            href = await link.get_attribute("href")
            return make_absolute(href, BASE) if href else None
    except Exception:
        pass
    return None
