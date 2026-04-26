"""
scraper_kominka_net.py — Scraper for https://kominka.net
Japan's largest kominka-specialist listing site.

Site structure (verified 2026-04):
  - Index: https://kominka.net/  (paginated: /page/2/, /page/3/ …)
  - Cards: div#masonry > div.col-sm-4.boxy  →  a[href*='/bukken/']
  - Detail: https://kominka.net/bukken/{id}/
  - robots.txt: only /wp-admin/ is Disallowed — root / is fully allowed
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
LIST_URL = f"{BASE_URL}/"          # Top page lists all kominka (paginated)
MAX_PAGES = 10


class KominkaNetScraper(BaseScraper):

    SOURCE_SITE = SOURCE_SITE
    BASE_URL = BASE_URL
    REQUEST_DELAY = 5.0

    # ── Override robots check ──────────────────────────────────
    # robots.txt only disallows /wp-admin/ — everything else is allowed.
    # We bypass the stdlib parser which mishandles minimal robots.txt files.

    def _is_allowed(self, url: str) -> bool:
        disallowed = ["/wp-admin/"]
        from urllib.parse import urlparse
        path = urlparse(url).path
        allowed = not any(path.startswith(p) for p in disallowed)
        if not allowed:
            logger.debug(f"[kominka.net] robots.txt blocks: {url}")
        return allowed

    # ── Step 1: Discover listing URLs ─────────────────────────

    def scrape_listing_urls(self) -> list[str]:
        urls: list[str] = []
        next_url: Optional[str] = LIST_URL
        page_num = 0

        while next_url and page_num < MAX_PAGES:
            self._rate_limit()
            logger.info(f"[kominka.net] Fetching index page {page_num + 1}: {next_url}")

            try:
                html = self._fetch_html(next_url)

                # ── DEBUG: show first 2000 chars of fetched HTML ──
                logger.debug(f"[kominka.net] HTML preview (first 2000 chars):\n{html[:2000]}")

                soup = BeautifulSoup(html, "lxml")

                page_urls = self._extract_listing_urls(soup, html)
                urls.extend(page_urls)
                logger.info(f"[kominka.net] Page {page_num + 1}: found {len(page_urls)} listing URLs")

                next_url = self._get_next_page_url(soup)
                page_num += 1

            except Exception as e:
                logger.error(f"[kominka.net] Error on index page {next_url}: {e}")
                break

        return list(dict.fromkeys(urls))

    def _extract_listing_urls(self, soup: BeautifulSoup, raw_html: str = "") -> list[str]:
        """Extract /bukken/{id}/ links from the listing index.

        Primary:   div#masonry a[href*='/bukken/']   (card container)
        Fallback1: div.boxy a[href*='/bukken/']
        Fallback2: any a[href*='/bukken/'] on the page
        Fallback3: regex on raw HTML
        """
        urls: list[str] = []
        seen: set[str] = set()

        def add(href: str) -> None:
            full = urljoin(BASE_URL, href).split("?")[0].rstrip("/") + "/"
            # Only /bukken/SOMETHING/ — not /category/bukken/
            if re.search(r"/bukken/[^/]+/$", full) and full not in seen:
                seen.add(full)
                urls.append(full)

        # Primary selector: masonry grid cards
        masonry = soup.select_one("#masonry")
        if masonry:
            for a in masonry.select("a[href*='/bukken/']"):
                add(a["href"])
            logger.debug(f"[kominka.net] #masonry selector → {len(urls)} links")

        # Fallback 1: boxy class (card wrapper)
        if not urls:
            for a in soup.select("div.boxy a[href*='/bukken/']"):
                add(a["href"])
            logger.debug(f"[kominka.net] div.boxy selector → {len(urls)} links")

        # Fallback 2: any anchor with /bukken/
        if not urls:
            for a in soup.select("a[href*='/bukken/']"):
                add(a.get("href", ""))
            logger.debug(f"[kominka.net] generic a[href] selector → {len(urls)} links")

        # Fallback 3: regex on raw HTML
        if not urls and raw_html:
            for href in re.findall(r'href=["\']((?:https://kominka\.net)?/bukken/[^"\']+)["\']', raw_html):
                add(href)
            logger.debug(f"[kominka.net] regex fallback → {len(urls)} links")

        logger.info(f"[kominka.net] Total unique /bukken/ links extracted: {len(urls)}")
        return urls

    def _get_next_page_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the 'next page' link — kominka.net uses /page/N/ (WordPress)."""
        # rel="next" (WordPress standard)
        tag = soup.find("a", rel="next")
        if tag and tag.get("href"):
            return urljoin(BASE_URL, tag["href"])

        # Text contains 次 + href has /page/
        for a in soup.select("a"):
            if "次" in a.get_text() and "/page/" in a.get("href", ""):
                return urljoin(BASE_URL, a["href"])

        return None

    # ── Step 2: Parse a detail page ───────────────────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")

        logger.debug(f"[kominka.net] Parsing detail page: {url}")
        logger.debug(f"[kominka.net] Detail HTML preview:\n{html[:1000]}")

        # Skip sold listings
        sold_kw = ["成約済", "売却済", "掲載終了", "募集終了", "SOLD OUT", "商談中"]
        page_text = soup.get_text()
        for kw in sold_kw:
            if kw in page_text:
                logger.info(f"[kominka.net] Skipping sold listing ({kw}): {url}")
                return None

        listing: dict = {}

        listing["title"] = self._extract_title(soup)
        if not listing["title"]:
            logger.warning(f"[kominka.net] No title at {url}")
            return None

        listing["price"] = self._extract_price(soup)

        pref, city, addr = self._extract_location(soup)
        listing["location_prefecture"] = pref
        listing["location_city"] = city
        listing["location_address"] = addr

        details = self._extract_detail_table(soup)
        listing["area_sqm"] = details.get("building_area")
        listing["land_area_sqm"] = details.get("land_area")
        listing["year_built"] = details.get("year_built")
        listing["agency_name"] = details.get("agency_name")
        listing["contact_phone"] = details.get("contact_phone")
        listing["contact_email"] = details.get("contact_email")

        listing["description"] = self._extract_description(soup)
        listing["images"] = self._extract_images(soup)

        logger.info(
            f"[kominka.net] Parsed: {listing['title']!r} | "
            f"{listing['location_prefecture']} | {listing['price']}万円"
        )
        return listing

    # ── Private helpers ───────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # kominka.net WordPress — h1.entry-title is the post title
        for sel in ["h1.entry-title", ".entry-title", "h1"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                # Strip leading item-number prefix like "204009[宮城県]"
                text = re.sub(r"^\d+\[[^\]]+\]\s*", "", text).strip()
                if text and "古民家住まいる" not in text:
                    return text

        # Fallback: parse <title> tag
        t = soup.find("title")
        if t:
            text = re.sub(r"\s*[–\-|｜]\s*古民家住まいる.*$", "", t.get_text()).strip()
            if text:
                return text
        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[int]:
        """Return price in 万円 (int). None = 要相談."""
        # Look in the posttitle / panel-body area first for accuracy
        for sel in [".panel-body", ".posttitle", ".entry-content", ".entry-header"]:
            el = soup.select_one(sel)
            if not el:
                continue
            text = el.get_text()
            m = re.search(r"([0-9,]+)\s*万円", text)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    pass

        # Page-wide fallback
        m = re.search(r"([0-9,]+)\s*万円", soup.get_text())
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _extract_location(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (prefecture, city, address)."""
        pref = city = addr = None

        # 1. post-category class (kominka.net card label)
        for sel in [".post-category", ".breadcrumb", "#breadcrumbs", "nav.breadcrumbs"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text()
                p, c, a = self._parse_japanese_address(text)
                if p:
                    return p, c, a

        # 2. WordPress category links contain prefecture name
        for a in soup.select("a[href*='/category/bukken/']"):
            text = a.get_text(strip=True)
            p, c, _ = self._parse_japanese_address(text + "県")  # hint
            if not p:
                p, c, _ = self._parse_japanese_address(text)
            if p:
                pref = p
                break

        # 3. Entry content text
        entry = soup.select_one(".entry-content, .panel-body, article")
        if entry:
            p, c, a = self._parse_japanese_address(entry.get_text())
            if p and not pref:
                pref, city, addr = p, c, a

        return pref, city, addr

    def _parse_japanese_address(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        pref = city = None
        address = text.strip()
        m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])", text)
        if m:
            pref = m.group(1)
            remainder = text[m.end():].strip()
            cm = re.match(r"([^\s]{2,8}[市区町村郡])", remainder)
            if cm:
                city = cm.group(1)
                address = remainder[cm.end():].strip()
            else:
                address = remainder
        return pref, city, address

    def _extract_detail_table(self, soup: BeautifulSoup) -> dict:
        details: dict = {}

        # dl > dt/dd
        for dt in soup.select("dl dt"):
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            if dd:
                self._map_label(details, label, dd.get_text(strip=True))

        # table tr > th/td
        for tr in soup.select("table tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if th and td:
                self._map_label(details, th.get_text(strip=True), td.get_text(strip=True), setdefault=True)

        # Regex fallback on entry-content text
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

    def _map_label(self, details: dict, label: str, value: str, setdefault: bool = False) -> None:
        set_ = details.setdefault if setdefault else details.__setitem__
        if any(k in label for k in ["建物面積", "床面積"]):
            set_("building_area", self._parse_area(value))
        elif any(k in label for k in ["土地面積", "敷地面積"]):
            set_("land_area", self._parse_area(value))
        elif any(k in label for k in ["築年", "建築年", "竣工"]):
            set_("year_built", self._parse_year(value))
        elif any(k in label for k in ["業者", "不動産", "仲介"]):
            set_("agency_name", value)
        elif "電話" in label or "TEL" in label.upper():
            set_("contact_phone", self._clean_phone(value))
        elif "メール" in label or "mail" in label.lower():
            set_("contact_email", value.strip())

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [".entry-content", ".panel-body", ".post-content", "article"]:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 30:
                for noise in el.select("nav, .sidebar, .widget, form, script, style, .post-category"):
                    noise.decompose()
                return el.get_text(separator="\n", strip=True)

        paragraphs = soup.find_all("p")
        if paragraphs:
            longest = max(paragraphs, key=lambda p: len(p.get_text()))
            text = longest.get_text(strip=True)
            if len(text) > 50:
                return text
        return None

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        images: list[str] = []

        for sel in [".panel-body img", ".entry-content img", "article img", ".content img"]:
            for img in soup.select(sel):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src and src not in seen:
                    full = urljoin(BASE_URL, src)
                    if not any(s in full for s in ["icon", "logo", "btn", "arrow", "banner", "soldout"]):
                        images.append(full)
                        seen.add(src)
        return images[:20]

    # ── Parsing utilities ─────────────────────────────────────

    def _parse_area(self, text: str) -> Optional[float]:
        m = re.search(r"([\d,]+\.?\d*)\s*[㎡m²]", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        m = re.search(r"([\d.]+)\s*坪", text)
        if m:
            try:
                return round(float(m.group(1)) * 3.306, 2)
            except ValueError:
                pass
        return None

    def _parse_year(self, text: str) -> Optional[int]:
        m = re.search(r"(19\d{2}|20[012]\d)\s*年?", text)
        if m:
            return int(m.group(1))
        era_map = {"令和": 2018, "平成": 1988, "昭和": 1925, "大正": 1911, "明治": 1867}
        for era, offset in era_map.items():
            m = re.search(rf"{era}\s*(\d+)\s*年?", text)
            if m:
                return offset + int(m.group(1))
        return None

    def _clean_phone(self, text: str) -> Optional[str]:
        m = re.search(r"[\d\-\(\)]{10,15}", text.replace(" ", ""))
        return m.group(0) if m else None
