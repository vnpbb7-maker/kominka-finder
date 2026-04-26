"""
scraper_kominka_net.py — Scraper for https://kominka.net
Japan's largest kominka-specialist listing site.

Target pages:
  - Top page / index: https://kominka.net/  (paginated: /page/2/, /page/3/ …)
  - Detail: https://kominka.net/bukken/{id}/

Selectors verified against live site as of 2026-04.
"""

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from scraper_base import BaseScraper

# ── Constants ─────────────────────────────────────────────────

SOURCE_SITE = "kominka.net"
BASE_URL = "https://kominka.net"

# Top page lists all recent kominka (paginated)
LIST_URL = f"{BASE_URL}/"

MAX_PAGES = 10


class KominkaNetScraper(BaseScraper):
    """
    Scrapes kominka.net listing index + detail pages.
    Full pipeline: url discovery → HTML fetch → parse → structured dict.
    """

    SOURCE_SITE = SOURCE_SITE
    BASE_URL = BASE_URL
    REQUEST_DELAY = 5.0  # 5 seconds between requests (be polite)

    # ── Step 1: Discover listing URLs ─────────────────────────

    def scrape_listing_urls(self) -> list[str]:
        """
        Paginate through the top-page listing index and collect detail-page URLs.
        Pagination: /page/2/, /page/3/, …
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

                page_urls = self._extract_listing_urls(soup)
                urls.extend(page_urls)
                logger.info(f"[kominka.net] Page {page_num + 1}: found {len(page_urls)} listings")

                next_url = self._get_next_page_url(soup)
                page_num += 1

            except Exception as e:
                logger.error(f"[kominka.net] Error on index page {next_url}: {e}")
                break

        return list(dict.fromkeys(urls))  # deduplicate preserving order

    def _extract_listing_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract detail-page hrefs from a listing index page.

        kominka.net detail URL pattern: /bukken/{id}/
        """
        urls = []

        for anchor in soup.select("a[href*='/bukken/']"):
            href = anchor.get("href", "")
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            # Normalise: strip query params, ensure trailing slash
            full_url = full_url.split("?")[0].rstrip("/") + "/"
            # Skip category/list pages like /category/bukken/
            if re.search(r"/bukken/[^/]+/$", full_url):
                urls.append(full_url)

        return urls

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the 'next page' link in pagination.

        kominka.net uses WordPress-style pagination: <a href="/page/N/">次のページ »</a>
        """
        # Pattern 1: rel="next" link (WordPress standard)
        next_link = soup.find("a", rel="next")
        if next_link and next_link.get("href"):
            return urljoin(BASE_URL, next_link["href"])

        # Pattern 2: anchor text containing '次'
        for anchor in soup.select("a"):
            text = anchor.get_text(strip=True)
            if "次" in text and anchor.get("href"):
                href = anchor["href"]
                if "/page/" in href:
                    return urljoin(BASE_URL, href)

        return None  # no more pages

    # ── Step 2: Parse a single listing detail page ────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        """
        Parse a kominka.net detail page into a structured dict.
        Returns None if the page is not a valid listing (e.g. 404, sold).
        """
        soup = BeautifulSoup(html, "lxml")

        # Guard: skip sold/removed listings
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

        # ── Property details (area, year built, agency) ──────
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
        """Extract the listing title.

        kominka.net uses h1.entry-title or the <title> tag minus the site suffix.
        """
        # WordPress entry title
        for selector in ["h1.entry-title", "h1", ".entry-title"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if text and "古民家住まいる" not in text:
                    return text

        # Fallback: strip site name from <title>
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove " – 古民家住まいる" suffix
            title = re.sub(r"\s*[–\-|｜]\s*古民家住まいる.*$", "", title).strip()
            if title:
                return title

        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract price in 万円. Returns None for '要相談' (negotiable)."""
        price_patterns = [
            r"([0-9,]+)\s*万円",
            r"([0-9,]+)\s*万",
        ]

        # Search in the full page text (kominka.net embeds price inside entry-content)
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
        """Return (prefecture, city, address) from the listing.

        kominka.net shows location in:
        - Breadcrumb: 東北 > 宮城 > 物件情報 > 売買物件
        - Entry text containing XX県 XX市 etc.
        """
        prefecture = city = address = None

        # 1. Try breadcrumb navigation
        breadcrumb = soup.select_one(".breadcrumb, nav.breadcrumbs, #breadcrumbs")
        if breadcrumb:
            text = breadcrumb.get_text()
            prefecture, city, address = self._parse_japanese_address(text)
            if prefecture:
                return prefecture, city, address

        # 2. Try WordPress category links (they include prefecture names)
        for anchor in soup.select("a[href*='/category/bukken/']"):
            text = anchor.get_text(strip=True)
            pref, cty, _ = self._parse_japanese_address(text)
            if pref:
                prefecture = pref
                break

        # 3. Search entry content for address-like strings
        entry = soup.select_one(".entry-content, article, .post-content")
        if entry:
            text = entry.get_text()
            p, c, a = self._parse_japanese_address(text)
            if p and not prefecture:
                prefecture, city, address = p, c, a

        return prefecture, city, address

    def _parse_japanese_address(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse a Japanese address string into (prefecture, city, remainder).
        """
        prefecture = city = None
        address = text.strip()

        pref_match = re.search(
            r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])", text
        )
        if pref_match:
            prefecture = pref_match.group(1)
            remainder = text[pref_match.end():].strip()

            city_match = re.match(r"([^\s]{2,8}[市区町村郡])", remainder)
            if city_match:
                city = city_match.group(1)
                address = remainder[city_match.end():].strip()
            else:
                address = remainder

        return prefecture, city, address

    def _extract_detail_table(self, soup: BeautifulSoup) -> dict:
        """
        Extract structured details from the property info table/body.
        kominka.net uses WordPress posts; details are in dt/dd or free text.
        """
        details: dict = {}

        # Try definition lists (dt/dd pattern)
        for dt in soup.select("dl dt"):
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            value = dd.get_text(strip=True)
            self._map_detail(details, label, value)

        # Try table rows (th/td pattern)
        for tr in soup.select("table tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if th and td:
                self._map_detail(details, th.get_text(strip=True), td.get_text(strip=True), setdefault=True)

        # Fallback: parse raw text from entry body for 建物面積 / 土地 etc.
        if not details:
            entry = soup.select_one(".entry-content, article")
            if entry:
                text = entry.get_text()
                for pattern, key, parser in [
                    (r"建物面積[：:]\s*([\d,.]+[㎡m²坪])", "building_area", self._parse_area),
                    (r"土地面積[：:]\s*([\d,.]+[㎡m²坪])", "land_area", self._parse_area),
                    (r"築年[：:]\s*(.{2,20}?年)", "year_built", self._parse_year),
                ]:
                    m = re.search(pattern, text)
                    if m:
                        details.setdefault(key, parser(m.group(1)))

        return details

    def _map_detail(self, details: dict, label: str, value: str, setdefault: bool = False) -> None:
        """Map a label/value pair into the details dict."""
        setter = details.setdefault if setdefault else details.__setitem__

        if any(k in label for k in ["建物面積", "床面積"]):
            setter("building_area", self._parse_area(value))
        elif any(k in label for k in ["土地面積", "敷地面積"]):
            setter("land_area", self._parse_area(value))
        elif any(k in label for k in ["築年", "建築年", "竣工"]):
            setter("year_built", self._parse_year(value))
        elif any(k in label for k in ["業者", "不動産", "仲介"]):
            setter("agency_name", value)
        elif "電話" in label or "TEL" in label.upper():
            setter("contact_phone", self._clean_phone(value))
        elif "メール" in label or "mail" in label.lower():
            setter("contact_email", value.strip())

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the listing description from the WordPress entry content."""
        # kominka.net uses .entry-content for the post body
        for selector in [".entry-content", ".post-content", "article .content", "article"]:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 30:
                # Remove navigation / sidebar noise
                for noise in el.select("nav, .sidebar, .widget, form, script, style"):
                    noise.decompose()
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
        """Extract listing image URLs."""
        seen: set[str] = set()
        images: list[str] = []

        # kominka.net images are in .entry-content or gallery blocks
        for selector in [".entry-content img", ".gallery img", "article img", "[class*='photo'] img"]:
            for img in soup.select(selector):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src and src not in seen:
                    full_url = urljoin(BASE_URL, src)
                    if not any(skip in full_url for skip in ["icon", "logo", "btn", "arrow", "banner"]):
                        images.append(full_url)
                        seen.add(src)

        # Generic fallback
        if not images:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if src and "." in src and src not in seen:
                    full_url = urljoin(BASE_URL, src)
                    images.append(full_url)
                    seen.add(src)

        return images[:20]

    # ── Parsing utilities ─────────────────────────────────────

    def _parse_area(self, text: str) -> Optional[float]:
        """Parse '125.50㎡' or '125.50m2' → 125.5."""
        m = re.search(r"([\d,]+\.?\d*)\s*[㎡m²]", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        # 坪 → ㎡ (1坪 = 3.306㎡)
        m = re.search(r"([\d.]+)\s*坪", text)
        if m:
            try:
                return round(float(m.group(1)) * 3.306, 2)
            except ValueError:
                pass
        return None

    def _parse_year(self, text: str) -> Optional[int]:
        """Parse year from Japanese era or Western year strings."""
        m = re.search(r"(19\d{2}|20[012]\d)\s*年?", text)
        if m:
            return int(m.group(1))

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
