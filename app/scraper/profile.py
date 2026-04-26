import logging
import re
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext

from app.scraper.browser import handle_age_gate

logger = logging.getLogger(__name__)

PHOTO_HOST = "a.rl.be"

LABEL_MAP = {
    "Geslacht": "gender",
    "Leeftijd": "age",
    "Geaardheid": "orientation",
    "Nationaliteit": "nationality",
    "Etniciteit": "ethnicity",
    "Talen": "languages",
    "Lengte": "height",
    "Gewicht": "weight",
    "Haarkleur": "hair",
    "Kleur ogen": "eyes",
    "Intiem kapsel": "intimate_grooming",
    "Cupmaat": "bust",
    "Formaat penis": "penis_size",
    "Tattoo(s)": "tattoos",
    "Piercing(s)": "piercings",
    "Roker": "smoker",
    "Stad": "location",
    "Gemeente": "location",
    "Locatie": "location",
    "Regio": "location",
}


@dataclass
class RawProfileData:
    source_url: str
    username: str = ""
    display_name: str = ""
    bio: str = ""
    phone: str = ""
    location: str = ""
    price: str = ""
    extra_data: dict = field(default_factory=dict)
    photo_urls: list[str] = field(default_factory=list)
    ad_urls: list[str] = field(default_factory=list)
    ad_details: dict = field(default_factory=dict)  # ad_url → {location, description, published_at_str}


async def scrape_profile(context: BrowserContext, url: str) -> RawProfileData:
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await handle_age_gate(page)

        # Wait for the profile accordion to render (it starts with opacity:0)
        try:
            await page.wait_for_selector("#rlProfileAccordion", timeout=8000)
            await page.wait_for_function(
                "() => { const el = document.querySelector('#rlProfileAccordion'); "
                "return el && el.style.opacity !== '0'; }",
                timeout=5000,
            )
        except Exception:
            pass

        data = RawProfileData(source_url=url)
        data.username = url.rstrip("/").split("/")[-1]

        # Name
        for selector in [".title-bar h1", ".mobile-article-title h1", "h1"]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    data.display_name = (await el.inner_text()).strip()
                    if data.display_name:
                        break
            except Exception:
                pass

        # Phone — read from DOM directly (element may be hidden in accordion)
        try:
            phone_href = await page.evaluate("""
                () => {
                    const a = document.querySelector('a[href^="tel:"]');
                    return a ? a.href : '';
                }
            """)
            if phone_href and phone_href.startswith("tel:"):
                data.phone = phone_href[4:].strip()
        except Exception:
            pass

        # Profile attributes (Geslacht, Leeftijd, etc.) via JS evaluation
        data.extra_data = await _extract_details(page)

        # Location: pop from extra_data if present (unlikely), else fetch from linked ad page
        data.location = data.extra_data.pop("location", "")

        # WhatsApp — read from DOM directly (element may be hidden)
        try:
            wa_href = await page.evaluate("""
                () => {
                    for (const a of document.querySelectorAll('a[href]')) {
                        if (a.href.includes('wa.me') || a.href.includes('whatsapp.com'))
                            return a.href;
                    }
                    return '';
                }
            """)
            if wa_href:
                m = re.search(r"wa\.me/(\d+)", wa_href)
                if m:
                    num = m.group(1)
                    if num.startswith("32") and len(num) > 10:
                        num = "0" + num[2:]
                    data.extra_data["whatsapp"] = num
        except Exception:
            pass

        # Tarieven (rates)
        await _extract_rates(page, data.extra_data)

        # Mogelijkheden (services)
        services = await _extract_services(page)
        if services:
            data.extra_data["services"] = services

        # Bio
        data.bio = await _extract_bio(page)

        # Price: first hourly incall rate for the grid overview
        data.price = (
            _first_rate(data.extra_data.get("price_incall", ""))
            or _first_rate(data.extra_data.get("price_outcall", ""))
        )

        # Photos: use fancybox gallery href (full resolution, always in static HTML)
        seen: set[str] = set()
        links = await page.locator("a[data-fancybox='gallery']").all()
        for link in links:
            href = await link.get_attribute("href") or ""
            if href and PHOTO_HOST in href and "/photos/" in href and href not in seen:
                seen.add(href)
                data.photo_urls.append(href)

        # All advertisement URLs (for archiving)
        ad_urls = await _find_all_ad_urls(page)
        data.ad_urls = ad_urls

        # Location: navigate to first ad page to get city
        if not data.location and ad_urls:
            ad_info = await scrape_ad_page(context, ad_urls[0])
            data.location = ad_info.get("location", "")
            data.ad_details[ad_urls[0]] = ad_info

        return data
    finally:
        await page.close()


async def _extract_details(page) -> dict:
    try:
        raw = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('#details-content .dl-item');
                const result = {};
                items.forEach(item => {
                    const b = item.querySelector('b');
                    const span = item.querySelector('span');
                    if (b && span) {
                        const key = b.textContent.trim().replace(/:$/, '').trim();
                        const val = span.textContent.trim();
                        if (val) result[key] = val;
                    }
                });
                return result;
            }
        """)
    except Exception:
        return {}

    extra = {}
    for dutch, value in (raw or {}).items():
        key = LABEL_MAP.get(dutch)
        if key and value:
            extra[key] = value
    return extra


async def _extract_rates(page, extra: dict):
    for section_id, key in [
        ("#rates-content-incall", "price_incall"),
        ("#rates-content-outcall", "price_outcall"),
    ]:
        try:
            result = await page.evaluate("""
                (sectionId) => {
                    const dl = document.querySelector(sectionId + ' dl.dl-horizontal');
                    if (!dl) return null;
                    const dts = Array.from(dl.querySelectorAll('dt'));
                    const dds = Array.from(dl.querySelectorAll('dd'));
                    const parts = [];
                    dts.forEach((dt, i) => {
                        const val = dds[i] ? dds[i].textContent.trim() : '';
                        if (val) parts.push(dt.textContent.trim().replace(/:$/, '') + ' ' + val);
                    });
                    return parts.length ? parts.join(' / ') : null;
                }
            """, section_id)
            if result:
                extra[key] = result
        except Exception:
            pass


async def _extract_services(page) -> dict:
    try:
        result = await page.evaluate("""
            () => {
                const pp = document.querySelector('#pp-content .card-body');
                if (!pp) return {};
                const out = {};
                pp.querySelectorAll('h4').forEach(h4 => {
                    const cat = h4.textContent.trim();
                    const ul = h4.nextElementSibling;
                    if (ul && ul.tagName === 'UL') {
                        const items = Array.from(ul.querySelectorAll('li'))
                            .map(li => li.textContent.trim())
                            .filter(t => t.length > 0);
                        if (items.length) out[cat] = items;
                    }
                });
                return out;
            }
        """)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


async def _find_all_ad_urls(page) -> list[str]:
    """Find all linked advertisement URLs from the profile page."""
    try:
        hrefs = await page.evaluate("""
            () => {
                const patterns = ['/prive-ontvangst/', '/escort/', '/massage/', '/shemale/'];
                const seen = new Set();
                const result = [];
                for (const a of document.querySelectorAll('a[href$=".html"]')) {
                    if (patterns.some(p => a.href.includes(p)) && !seen.has(a.href)) {
                        seen.add(a.href);
                        result.push(a.href);
                    }
                }
                return result;
            }
        """)
        return [h.strip() for h in (hrefs or []) if h.strip()]
    except Exception:
        return []


async def scrape_ad_page(context: BrowserContext, ad_url: str) -> dict:
    """Visit an ad page; return {location, description, published_at_str}."""
    page = await context.new_page()
    try:
        await page.goto(ad_url, wait_until="domcontentloaded", timeout=15000)
        await handle_age_gate(page)
        result = await page.evaluate("""
            () => {
                const locEl = document.querySelector('.article-subtitle a[href*="/regio/"]');
                const location = locEl ? locEl.textContent.trim() : '';

                const descCandidates = [
                    '.description-body', '#description-content',
                    '.article-body', '[class*="omschrijving"]',
                ];
                let description = '';
                for (const sel of descCandidates) {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const paras = Array.from(el.querySelectorAll('p'))
                        .map(p => p.textContent.trim()).filter(t => t.length > 5);
                    description = paras.length ? paras.join('\\n\\n') : el.textContent.trim();
                    if (description) break;
                }

                let published_at_str = '';
                const subtitle = document.querySelector('.article-subtitle');
                if (subtitle) {
                    const m = subtitle.textContent.match(/\\d{1,2}[\\/\\.\\-]\\d{1,2}[\\/\\.\\-]\\d{2,4}/);
                    if (m) published_at_str = m[0];
                }
                if (!published_at_str) {
                    const t = document.querySelector('time[datetime]');
                    if (t) published_at_str = t.getAttribute('datetime') || '';
                }
                if (!published_at_str) {
                    const m2 = document.querySelector('meta[itemprop="datePublished"]');
                    if (m2) published_at_str = m2.getAttribute('content') || '';
                }

                return { location, description, published_at_str };
            }
        """)
        return result or {}
    except Exception:
        return {}
    finally:
        await page.close()


async def _extract_bio(page) -> str:
    try:
        bio = await page.evaluate("""
            () => {
                const candidates = [
                    '.description-body',
                    '[class*="description-body"]',
                    '#description-content',
                    '[class*="omschrijving"]',
                    '[class*="profiel-tekst"]',
                    '.profile-description',
                ];
                for (const sel of candidates) {
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const paras = Array.from(el.querySelectorAll('p:not(.text-muted)'));
                    const text = paras.map(p => p.textContent.trim()).filter(t => t.length > 5).join('\\n\\n');
                    if (text.length > 10) return text;
                    // fallback: whole element text
                    const raw = el.textContent.trim();
                    if (raw.length > 10) return raw;
                }
                return '';
            }
        """)
        return (bio or "").strip()
    except Exception:
        return ""


def _first_rate(rates_str: str) -> str:
    """Extract first rate from '1 uur €220 / 2 uren €400' → '€220'"""
    if not rates_str:
        return ""
    m = re.search(r"(€\s*[\d.,]+)", rates_str.split("/")[0])
    return m.group(1).replace(" ", "") if m else ""
