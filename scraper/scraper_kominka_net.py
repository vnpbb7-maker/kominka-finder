"""
scraper_kominka_net.py — Scraper for https://www.kominka.net
Japan's largest kominka-specialist listing site.

Target pages:
  - Index: https://www.kominka.net/list/ (paginated search results)
  - Detail: https://www.kominka.net/item/{id}/

Selectors verified against site structure as of 2025-04.
If selectors break, check the CSS classes on the live site.
"""

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from scraper_base import BaseScraper

# ── Constants ─────────────────────────────────────────────────

SOURCE_SITE = "kominka.net"
BASE_URL = "https://www.kominka.net"

# Start from all-Japan listing sorted by newest
LIST_URL = f"{BASE_URL}/list/?sort=new"

# Max pages to scrape per run (safety cap; ~20 listings/page = 200 listings/run)
MAX_PAGES = 10


class KominkaNetScraper(BaseScraper):
    """
    Scrapes kominka.net listing index + detail pages.
    Full pipeline: url discovery → HTML fetch → parse → structured dict.
    """

    SOURCE_SITE = SOURCE_SITE
    BASE_URL = BASE_URL
    REQUEST_DELAY = 5.0  # 5 seconds between requests

    # ── Step 1: Discover listing URLs ─────────────────────────

    def scrape_listing_urls(self) -> list[str]:
        """
        Paginate through the listing index and collect all detail-page URLs.
        Stops at MAX_PAGES or when no more 'next page' link is found.
        """
        urls: list[str] = []
        next_url: Optional[str] = LIST_URL
        page_num = 0

        while next_url and page_num < MAX_PAGES:
            if not self._is_allowed(next_url):
                logger.warning(f"robots.txt disallows index page: {next_url}")
                break

            self._rate_limit()
            logger.info(f"[kominka.net] Fetching index page {page_num + 1}: {next_url}")

            try:
                html = self._fetch_html(next_url)
                soup = BeautifulSoup(html, "lxml")

                # Extract listing card links
                page_urls = self._extract_listing_urls(soup)
                urls.extend(page_urls)
                logger.info(f"[kominka.net] Page {page_num + 1}: found {len(page_urls)} listings")

                # Find next page link
                next_url = self._get_next_page_url(soup)
                page_num += 1

            except Exception as e:
                logger.error(f"[kominka.net] Error on index page {next_url}: {e}")
                break

        return list(dict.fromkeys(urls))  # deduplicate preserving order

    def _extract_listing_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract detail-page hrefs from a listing index page."""
        urls = []

        # kominka.net listing cards link pattern: /item/{id}/
        for anchor in soup.select("a[href*='/item/']"):
            href = anchor.get("href", "")
            if href:
                full_url = urljoin(BASE_URL, href)
                # Clean URL: remove query params from detail pages
                full_url = full_url.split("?")[0].rstrip("/") + "/"
                urls.append(full_url)

        return urls

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the 'next page' link in pagination."""
        # Try common pagination patterns
        # Pattern 1: rel="next" link
        next_link = soup.find("a", rel="next")
        if next_link and next_link.get("href"):
            return urljoin(BASE_URL, next_link["href"])

        # Pattern 2: pagination list with '次へ' text
        for anchor in soup.select("a"):
            text = anchor.get_text(strip=True)
            if text in ("次へ", "次のページ", "›", ">>"):
                href = anchor.get("href")
                if href:
                    return urljoin(BASE_URL, href)

        return None  # no more pages

    # ── Step 2: Parse a single listing detail page ────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        """
        Parse a kominka.net detail page into a structured dict.
        Returns None if the page is not a valid listing (e.g. 404, sold).
        """
        soup = BeautifulSoup(html, "lxml")

        # Guard: skip if listing is sold / removed
        if self._is_sold(soup):
            logger.info(f"[kominka.net] Listing sold/removed: {url}")
            return None

        listing: dict = {}

        # ── Title ────────────────────────────────────────────
        listing["title"] = self._extract_title(soup)
        if not listing["title"]:
            logger.warning(f"[kominka.net] No title found at {url}")
            return None

        # ── Price ────────────────────────────────────────────
        listing["price"] = self._extract_price(soup)

        # ── Location ─────────────────────────────────────────
        prefecture, city, address = self._extract_location(soup)
        listing["location_prefecture"] = prefecture
        listing["location_city"] = city
        listing["location_address"] = address

        # ── Property details ──────────────────────────────────
        details = self._extract_detail_table(soup)
        listing["area_sqm"] = details.get("building_area")
        listing["land_area_sqm"] = details.get("land_area")
        listing["year_built"] = details.get("year_built")
        listing["agency_name"] = details.get("agency_name")
        listing["contact_phone"] = details.get("contact_phone")
        listing["contact_email"] = details.get("contact_email")

        # ── Description ───────────────────────────────────────
        listing["description"] = self._extract_description(soup)

        # ── Images ───────────────────────────────────────────
        listing["images"] = self._extract_images(soup)

        return listing

    # ── Private parsing helpers ───────────────────────────────

    def _is_sold(self, soup: BeautifulSoup) -> bool:
        """Detect if the listing is sold/removed/unavailable."""
        sold_keywords = ["成約済", "売却済", "掲載終了", "募集終了", "SOLD", "商談中"]
        page_text = soup.get_text()
        return any(kw in page_text for kw in sold_keywords)

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # Try h1 first, then common title selectors
        for selector in ["h1", ".property-title", ".item-title", ".bukken-title"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract price in 万円. Returns None for '要相談' (negotiable)."""
        price_patterns = [
            r"([0-9,]+)\s*万円",
            r"([0-9,]+)\s*万",
        ]
        price_selectors = [
            ".price", ".item-price", ".bukken-kakaku",
            "[class*='price']", "[class*='kakaku']"
        ]

        for selector in price_selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text()
                for pattern in price_patterns:
                    m = re.search(pattern, text)
                    if m:
                        return int(m.group(1).replace(",", ""))

        # Fallback: search entire page text
        page_text = soup.get_text()
        for pattern in price_patterns:
            m = re.search(pattern, page_text)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    pass

        return None  # 要相談 or not found

    def _extract_location(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (prefecture, city, address) from the listing."""
        prefecture = city = address = None

        # Try structured location fields first
        for selector in [".location", ".address", ".bukken-address", "[class*='address']"]:
            el = soup.select_one(selector)
            if el:
                full_text = el.get_text(strip=True)
                prefecture, city, address = self._parse_japanese_address(full_text)
                if prefecture:
                    break

        # Fallback: look for 都道府県 patterns in breadcrumb or meta tags
        if not prefecture:
            breadcrumb = soup.select_one("nav[aria-label='breadcrumb'], .breadcrumb, .breadcrumbs")
            if breadcrumb:
                text = breadcrumb.get_text()
                prefecture, city, _ = self._parse_japanese_address(text)

        return prefecture, city, address

    def _parse_japanese_address(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse a Japanese address string into (prefecture, city, remainder).
        Handles: 東京都, 大阪府, 京都府, XX県
        """
        prefecture = None
        city = None
        address = text.strip()

        # Extract prefecture
        pref_match = re.search(
            r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])", text
        )
        if pref_match:
            prefecture = pref_match.group(1)
            remainder = text[pref_match.end():].strip()

            # Extract city/town (市区町村)
            city_match = re.match(r"([^\s]{2,8}[市区町村郡])", remainder)
            if city_match:
                city = city_match.group(1)
                address = remainder[city_match.end():].strip()
            else:
                address = remainder

        return prefecture, city, address

    def _extract_detail_table(self, soup: BeautifulSoup) -> dict:
        """
        Extract structured details from the property info table.
        Returns a dict with building_area, land_area, year_built, agency etc.
        """
        details: dict = {}

        # Try definition lists (dt/dd pattern, common in Japanese RE sites)
        dts = soup.select("dl dt")
        for dt in dts:
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            value = dd.get_text(strip=True)

            if any(k in label for k in ["建物面積", "床面積"]):
                details["building_area"] = self._parse_area(value)
            elif any(k in label for k in ["土地面積", "敷地面積"]):
                details["land_area"] = self._parse_area(value)
            elif any(k in label for k in ["築年", "建築年", "竣工"]):
                details["year_built"] = self._parse_year(value)
            elif any(k in label for k in ["業者", "不動産会社", "仲介"]):
                details["agency_name"] = value
            elif "電話" in label or "TEL" in label.upper():
                details["contact_phone"] = self._clean_phone(value)
            elif "メール" in label or "mail" in label.lower():
                details["contact_email"] = value.strip()

        # Also try table rows (th/td pattern)
        trs = soup.select("table tr")
        for tr in trs:
            th = tr.select_one("th")
            td = tr.select_one("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            if any(k in label for k in ["建物面積", "床面積"]):
                details.setdefault("building_area", self._parse_area(value))
            elif any(k in label for k in ["土地面積", "敷地面積"]):
                details.setdefault("land_area", self._parse_area(value))
            elif any(k in label for k in ["築年", "建築年"]):
                details.setdefault("year_built", self._parse_year(value))
            elif any(k in label for k in ["業者", "不動産"]):
                details.setdefault("agency_name", value)
            elif "電話" in label:
                details.setdefault("contact_phone", self._clean_phone(value))

        return details

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the listing description / PR text."""
        for selector in [
            ".description", ".item-description", ".bukken-note",
            ".pr-text", "[class*='description']", "[class*='comment']",
            ".property-detail", "article",
        ]:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 30:
                return el.get_text(separator="\n", strip=True)

        # Fallback: largest <p> block
        paragraphs = soup.find_all("p")
        if paragraphs:
            longest = max(paragraphs, key=lambda p: len(p.get_text()))
            text = longest.get_text(strip=True)
            if len(text) > 50:
                return text

        return None

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        """Extract all listing image URLs."""
        seen = set()
        images = []

        # Target: <img> tags in known photo containers
        for selector in [".photo", ".gallery", ".images", "[class*='photo']", "[class*='gallery']"]:
            for img in soup.select(f"{selector} img"):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src and src not in seen:
                    full_url = urljoin(BASE_URL, src)
                    # Skip tiny icons/logos (less than 5KB threshold — check by URL pattern)
                    if not any(skip in full_url for skip in ["icon", "logo", "btn", "arrow"]):
                        images.append(full_url)
                        seen.add(src)

        # If no gallery found, grab all page images as fallback
        if not images:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if src and "." in src and src not in seen:
                    full_url = urljoin(BASE_URL, src)
                    images.append(full_url)
                    seen.add(src)

        return images[:20]  # cap at 20 images per listing

    # ── Parsing utilities ─────────────────────────────────────

    def _parse_area(self, text: str) -> Optional[float]:
        """Parse '125.50㎡' or '125.50m2' → 125.5."""
        m = re.search(r"([\d,]+\.?\d*)\s*[㎡m²]", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        # Try 坪 → ㎡ conversion (1坪 = 3.306㎡)
        m = re.search(r"([\d.]+)\s*坪", text)
        if m:
            try:
                return round(float(m.group(1)) * 3.306, 2)
            except ValueError:
                pass
        return None

    def _parse_year(self, text: str) -> Optional[int]:
        """Parse year from Japanese era or Western year strings."""
        # Western year: 1980年, 2005年
        m = re.search(r"(19\d{2}|20[012]\d)\s*年?", text)
        if m:
            return int(m.group(1))

        # Japanese era → western year
        era_map = {
            "令和": 2018, "平成": 1988, "昭和": 1925,
            "大正": 1911, "明治": 1867,
        }
        for era_name, offset in era_map.items():
            m = re.search(rf"{era_name}\s*(\d+)\s*年?", text)
            if m:
                return offset + int(m.group(1))

        return None

    def _clean_phone(self, text: str) -> Optional[str]:
        """Extract and clean a phone number from text."""
        m = re.search(r"[\d\-\(\)]{10,15}", text.replace(" ", ""))
        return m.group(0) if m else None
