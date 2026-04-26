"""
scraper_smout.py — Scraper for https://smout.jp
Smout is Japan's largest rural-living / migration platform with kominka/akiya listings.

Site structure (verified 2026-04):
  - Search: https://smout.jp/plans?keyword=古民家&order=new  (SSR Nuxt, links in HTML)
  - Also:   https://smout.jp/plans?tag_ids=180  (tag: 空き家)
  - Detail: https://smout.jp/plans/{id}
  - Pagination: ?page=2
  - robots.txt: no Disallow for /plans/
"""

import re
from typing import Optional
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from scraper_base import BaseScraper
import db as _db

# ── Constants ──────────────────────────────────────────────────────────────────

SOURCE_SITE = "smout.jp"
BASE_URL = "https://smout.jp"
MAX_PAGES = 10

# Search queries that target kominka / akiya listings
SEARCH_QUERIES = [
    {"keyword": "古民家", "order": "new"},
    {"keyword": "空き家", "order": "new"},
    {"tag_ids": "180"},   # tag: 空き家
    {"tag_ids": "25"},    # tag: 田舎暮らし
]

SOLD_KEYWORDS = [
    "募集終了", "受付終了", "定員に達し", "終了しました",
    "SOLD OUT", "成約済", "売却済", "掲載終了",
]


class SmoutScraper(BaseScraper):

    SOURCE_SITE = SOURCE_SITE
    BASE_URL    = BASE_URL
    REQUEST_DELAY = 5.0

    # ── Step 1: Discover listing URLs ─────────────────────────────────────────

    def scrape_listing_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for query in SEARCH_QUERIES:
            for page in range(1, MAX_PAGES + 1):
                self._rate_limit()
                params = {**query, "page": str(page)}
                search_url = f"{BASE_URL}/plans?{urlencode(params)}"
                logger.info(f"[smout.jp] Fetching: {search_url}")

                try:
                    html = self._fetch_html(search_url)
                    soup = BeautifulSoup(html, "lxml")
                    page_urls = self._extract_listing_urls(soup, html)

                    new_on_page = [u for u in page_urls if u not in seen]
                    if not new_on_page:
                        logger.info(f"[smout.jp] No new URLs on page {page} — stopping pagination")
                        break

                    urls.extend(new_on_page)
                    seen.update(new_on_page)
                    logger.info(f"[smout.jp] Page {page}: +{len(new_on_page)} URLs (total {len(urls)})")

                except Exception as e:
                    logger.error(f"[smout.jp] Error fetching {search_url}: {e}")
                    break

        logger.info(f"[smout.jp] Found {len(urls)} total listing URLs")
        return urls

    def _extract_listing_urls(self, soup: BeautifulSoup, raw_html: str = "") -> list[str]:
        """Extract /plans/{id} links from a search result page."""
        urls: list[str] = []
        seen: set[str] = set()

        # Primary: anchor tags with /plans/\d+ pattern
        for a in soup.select("a[href*='/plans/']"):
            href = a.get("href", "")
            if re.search(r"/plans/\d+", href):
                full = urljoin(BASE_URL, href).split("?")[0]
                if full not in seen:
                    seen.add(full)
                    urls.append(full)

        # Fallback: regex on raw HTML
        if not urls:
            for m in re.finditer(r'href=["\'](/plans/(\d+))["\']', raw_html):
                full = f"{BASE_URL}{m.group(1)}"
                if full not in seen:
                    seen.add(full)
                    urls.append(full)

        # Filter: exclude tag/search pages, keep only numeric plan IDs
        urls = [u for u in urls if re.search(r"/plans/\d+$", u)]
        return urls

    # ── Step 2: Parse a detail page ───────────────────────────────────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")

        logger.debug(f"[smout.jp] Parsing: {url}")

        # Sold detection
        page_text = soup.get_text()
        for kw in SOLD_KEYWORDS:
            if kw in page_text:
                logger.info(f"[smout.jp] SOLD OUT ({kw}): {url}")
                self._mark_sold(url)
                return None

        listing: dict = {}

        listing["title"]       = self._extract_title(soup)
        if not listing["title"]:
            logger.warning(f"[smout.jp] No title: {url}")
            return None

        listing["price"]       = self._extract_price(soup)
        pref, city, addr       = self._extract_location(soup)
        listing["location_prefecture"] = pref
        listing["location_city"]       = city
        listing["location_address"]    = addr
        listing["description"] = self._extract_description(soup)
        listing["images"]      = self._extract_images(soup)

        logger.info(
            f"[smout.jp] Parsed: {listing['title'][:40]!r} | "
            f"{listing['location_prefecture']} {listing['location_city']} | "
            f"{listing['price']}万円"
        )
        return listing

    # ── Private helpers ────────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # smout uses <h1 class="title"> or <title>Plan title - smout</title>
        for sel in ["h1.title", "h1.plan-title", ".plan-header h1", "h1"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text and "smout" not in text.lower():
                    return text

        t = soup.find("title")
        if t:
            text = re.sub(r"\s*[\|｜\-–]\s*smout.*$", "", t.get_text(), flags=re.IGNORECASE).strip()
            if text:
                return text
        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[int]:
        page_text = soup.get_text()
        m = re.search(r"([0-9,]+)\s*万円", page_text)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _extract_location(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str], Optional[str]]:
        page_text = soup.get_text()

        pref = city = None

        # smout uses .city class: "千葉県勝浦市"
        for sel in [".city", ".prefecture", ".location", ".area", "[class*='pref']"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                p, c, _ = self._parse_japanese_address(text)
                if p:
                    return p, c, None

        # Fallback: scan full text
        p, c, _ = self._parse_japanese_address(page_text)
        return p or pref, c or city, None

    def _parse_japanese_address(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        pref = city = None
        m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])", text)
        if m:
            pref = m.group(1)
            remainder = text[m.end():].strip()
            cm = re.match(r"([^\s]{2,8}[市区町村郡])", remainder)
            if cm:
                city = cm.group(1)
        return pref, city, None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [".plan-detail", ".plan-description", ".description",
                    ".plan-body", "article", "main"]:
            el = soup.select_one(sel)
            if el:
                for noise in el.select("nav, .sidebar, script, style, .tags, form"):
                    noise.decompose()
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 50:
                    return text[:3000]
        return None

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        images: list[str] = []
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src or src in seen:
                continue
            if any(skip in src for skip in ["icon", "logo", "avatar", "banner", "btn"]):
                continue
            # smout uses imgix CDN
            if "imgix" in src or "smout" in src or src.startswith("http"):
                full = urljoin(BASE_URL, src)
                images.append(full)
                seen.add(src)
        return images[:15]

    def _mark_sold(self, url: str) -> None:
        """Mark listing is_active=False in DB. No-op if not yet in DB."""
        try:
            client = _db.get_client()
            _db.mark_inactive(client, url)
        except Exception as e:
            logger.warning(f"[smout.jp] Could not mark inactive: {e}")
