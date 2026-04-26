import logging
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

AGE_GATE_SELECTORS = [
    "a[href*='adult=1']",
    "a:has-text('Akkoord')",
    "button:has-text('Akkoord')",
    "button:has-text('I am 18')",
    "button:has-text('18+')",
    "a:has-text('I am 18')",
    "a:has-text('Enter')",
    "[data-testid='age-gate-confirm']",
]


@asynccontextmanager
async def managed_browser():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="nl-BE",
        )
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def handle_age_gate(page: Page) -> None:
    for selector in AGE_GATE_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)
                logger.info("Leeftijdsverificatie doorlopen via selector: %s", selector)
                return
        except Exception:
            continue


def make_absolute(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    from urllib.parse import urljoin
    return urljoin(base_url, href)
