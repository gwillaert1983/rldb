import logging

from playwright.async_api import BrowserContext

from app.scraper.browser import handle_age_gate, make_absolute
from app.scraper.listing import _find_next_page, _is_profile_url

logger = logging.getLogger(__name__)

BASE = "https://www.redlights.be"


async def collect_profile_urls_from_city(
    context: BrowserContext,
    city_url: str,
    max_pages: int = 5,
) -> list[str]:
    """
    Collect profile URLs from a redlights.be city listing page (regio/{province}/{city}.html).
    Works the same as collect_profile_urls in listing.py but starts from a city URL.
    """
    await context.add_cookies([{
        "name": "agecheck",
        "value": "1",
        "domain": ".redlights.be",
        "path": "/",
    }])

    page = await context.new_page()
    urls: list[str] = []
    current_url = city_url
    page_num = 1

    try:
        while current_url:
            if max_pages and page_num > max_pages:
                logger.info("Pagina-limiet bereikt (%d) voor %s", max_pages, city_url)
                break

            logger.info("Profielen ophalen pagina %d: %s", page_num, current_url)
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error("Fout bij ophalen %s: %s", current_url, e)
                break

            if page_num == 1:
                await handle_age_gate(page)

            links = await page.locator("a[href*='/profiel/']").all()
            found = 0
            for link in links:
                href = await link.get_attribute("href")
                if href and _is_profile_url(href):
                    urls.append(make_absolute(href, BASE))
                    found += 1

            logger.info("  %d profielen gevonden op pagina %d", found, page_num)

            current_url = await _find_next_page(page, page_num)
            page_num += 1
    finally:
        await page.close()

    deduped = list(dict.fromkeys(urls))
    logger.info("Totaal unieke profiel-URLs voor %s: %d", city_url, len(deduped))
    return deduped


async def collect_ad_urls_from_listing(
    context: BrowserContext,
    listing_url: str,
    categories: list[str] | None = None,
    max_pages: int = 0,
) -> list[str]:
    """
    Collect ad URLs from a redlights.be city listing page (regio/{province}/{city}.html).

    categories: filter by URL path segment, e.g. ["escort", "prive-ontvangst"].
                None or empty = include all categories.
    max_pages:  0 = unlimited.
    """
    await context.add_cookies([{
        "name": "agecheck",
        "value": "1",
        "domain": ".redlights.be",
        "path": "/",
    }])

    page = await context.new_page()
    urls: list[str] = []
    page_num = 1
    current_url = listing_url

    try:
        while current_url:
            if max_pages and page_num > max_pages:
                logger.info("Pagina-limiet bereikt (%d) voor %s", max_pages, listing_url)
                break

            logger.info("Advertentielisting pagina %d: %s", page_num, current_url)
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.error("Fout bij ophalen %s: %s", current_url, e)
                break

            if page_num == 1:
                await handle_age_gate(page)

            # Wait for JavaScript to render the article listing cards
            try:
                await page.wait_for_selector('.article-item a[href$=".html"]', timeout=10000)
            except Exception:
                pass  # Page may have no results; continue anyway

            # Collect all .html ad links on this page
            found_urls = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href$=".html"]'))
                    .map(a => a.href)
                    .filter(h => h.includes('redlights.be') && !h.includes('/regio/'))
            """)

            found = 0
            for href in (found_urls or []):
                if _is_ad_url(href) and _matches_category(href, categories):
                    urls.append(href)
                    found += 1

            logger.info("  %d advertentie-URLs gevonden op pagina %d", found, page_num)

            next_url = await _find_next_page(page, page_num)
            current_url = next_url
            page_num += 1
    finally:
        await page.close()

    deduped = list(dict.fromkeys(urls))
    logger.info("Totaal unieke advertentie-URLs: %d", len(deduped))
    return deduped


async def collect_ad_urls_from_search(
    context: BrowserContext,
    search_query: str,
    categories: list[str] | None = None,
) -> list[str]:
    """
    Collect ad URLs from the redlights.be search page (/zoeken/?q=...).
    Content is server-rendered; no pagination on the search page.
    """
    import urllib.parse

    await context.add_cookies([{
        "name": "agecheck",
        "value": "1",
        "domain": ".redlights.be",
        "path": "/",
    }])

    url = f"{BASE}/zoeken/?q={urllib.parse.quote(search_query)}"
    page = await context.new_page()
    try:
        logger.info("Zoeken op site: %s", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.error("Fout bij ophalen zoekpagina %s: %s", url, e)
            return []

        await handle_age_gate(page)

        try:
            await page.wait_for_selector('.article-item a[href$=".html"]', timeout=8000)
        except Exception:
            pass

        found_urls = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href$=".html"]'))
                .map(a => a.href)
                .filter(h => h.includes('redlights.be') && !h.includes('/regio/'))
        """)

        urls = []
        for href in (found_urls or []):
            if _is_ad_url(href) and _matches_category(href, categories):
                urls.append(href)

        deduped = list(dict.fromkeys(urls))
        logger.info("  %d advertentie-URLs gevonden via zoeken op '%s'", len(deduped), search_query)
        return deduped
    finally:
        await page.close()


async def get_province_city_urls(province_slug: str) -> list[str]:
    """
    Fetch city listing URLs for a province by scraping /regio/{province}/.
    Returns list of absolute city page URLs.
    """
    import httpx
    import re

    url = f"{BASE}/regio/{province_slug}/"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Cookie": "agecheck=1"})
            html = resp.text
    except Exception as e:
        logger.error("Fout bij ophalen provincie-steden %s: %s", province_slug, e)
        return []

    pattern = rf'href="({re.escape(BASE)}/regio/{re.escape(province_slug)}/[^"]+\.html)"'
    return list(dict.fromkeys(re.findall(pattern, html)))


def _is_ad_url(href: str) -> bool:
    """True for /category/[subcategory/]slug.html style ad URLs, not regio or profiel pages."""
    path = href.split("?")[0]
    if not path.endswith(".html"):
        return False
    if "/regio/" in path or "/profiel/" in path:
        return False
    parts = [p for p in path.rstrip("/").split("/") if p]
    # Need at least 2 parts: category + slug (e.g. massage/foo.html)
    return len(parts) >= 2


def _matches_category(href: str, categories: list[str] | None) -> bool:
    """Return True if the URL path starts with one of the given categories (or no filter)."""
    if not categories:
        return True
    path = href.split("?")[0].lower()
    return any(f"/{cat.lower()}/" in path for cat in categories)
