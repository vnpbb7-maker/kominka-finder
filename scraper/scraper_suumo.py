"""
scraper_suumo.py — Scraper for SUUMO 中古一戸建て (kominka keyword search)
https://suumo.jp/

Targets: 静岡県(shizuoka)・千葉県(chiba)・山梨県(yamanashi) + 古民家 keyword.
robots.txt: /chukoikkodate/ is not disallowed.

Site structure (verified 2026-04):
  - List: https://suumo.jp/chukoikkodate/{pref}/?kw=古民家&page=1
  - Links: /chukoikkodate/{pref}/sc_{city}/nc_{id}/
  - Detail: https://suumo.jp/chukoikkodate/{pref}/sc_{city}/nc_{id}/
"""

import re
import time
from typing import Optional
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from scraper_base import BaseScraper
import db as _db

# ── Constants ──────────────────────────────────────────────────────────────────

SOURCE_SITE = "suumo.jp"
BASE_URL    = "https://suumo.jp"
MAX_PAGES   = 15   # each page has ~10 listings

# Prefectures to search — SUUMO uses Japanese romanized names in URL
PREFECTURES = [
    ("shizuoka", "静岡県"),
    ("chiba",    "千葉県"),
    ("yamanashi","山梨県"),
]

SOLD_KEYWORDS = [
    "成約済", "ご成約", "売却済", "売れました", "掲載終了",
    "募集終了", "受付終了", "商談中", "SOLD OUT",
]


class SuumoScraper(BaseScraper):

    SOURCE_SITE = SOURCE_SITE
    BASE_URL    = BASE_URL
    REQUEST_DELAY = 5.0

    # ── Step 1: Discover listing URLs ─────────────────────────────────────────

    def scrape_listing_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for pref_slug, pref_name in PREFECTURES:
            logger.info(f"[suumo.jp] Searching {pref_name} ({pref_slug})")
            for page in range(1, MAX_PAGES + 1):
                self._rate_limit()
                params = {"kw": "古民家", "page": str(page)}
                list_url = f"{BASE_URL}/chukoikkodate/{pref_slug}/?{urlencode(params)}"
                logger.info(f"[suumo.jp] Fetching page {page}: {list_url}")

                try:
                    html = self._fetch_html(list_url)
                    soup = BeautifulSoup(html, "lxml")
                    page_urls = self._extract_listing_urls(soup)

                    new_urls = [u for u in page_urls if u not in seen]
                    if not new_urls:
                        logger.info(f"[suumo.jp] No new URLs on page {page} for {pref_name} — stopping")
                        break

                    urls.extend(new_urls)
                    seen.update(new_urls)
                    logger.info(f"[suumo.jp] {pref_name} page {page}: +{len(new_urls)} URLs (total {len(urls)})")

                except Exception as e:
                    logger.error(f"[suumo.jp] Error on {list_url}: {e}")
                    break

        logger.info(f"[suumo.jp] Found {len(urls)} total listing URLs")
        return urls

    def _extract_listing_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract /chukoikkodate/…/nc_NNNN/ links from a list page."""
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/nc_']"):
            href = a.get("href", "")
            if re.search(r"/nc_\d+/", href):
                full = urljoin(BASE_URL, href).split("?")[0]
                if not full.endswith("/"):
                    full += "/"
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
        return urls

    # ── Step 2: Parse a detail page ───────────────────────────────────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")
        logger.debug(f"[suumo.jp] Parsing: {url}")

        # Sold detection
        page_text = soup.get_text()
        for kw in SOLD_KEYWORDS:
            if kw in page_text:
                logger.info(f"[suumo.jp] SOLD OUT ({kw}): {url}")
                self._mark_sold(url)
                return None

        listing: dict = {}
        listing["title"]            = self._extract_title(soup)
        if not listing["title"]:
            logger.warning(f"[suumo.jp] No title: {url}")
            return None

        listing["price"]            = self._extract_price(soup, page_text)
        pref, city, addr            = self._extract_location(soup, page_text)
        listing["location_prefecture"] = pref
        listing["location_city"]       = city
        listing["location_address"]    = addr

        details                     = self._extract_detail_table(soup)
        listing["area_sqm"]         = details.get("building_area")
        listing["land_area_sqm"]    = details.get("land_area")
        listing["year_built"]       = details.get("year_built")
        listing["agency_name"]      = details.get("agency_name")

        listing["description"]      = self._extract_description(soup)
        listing["images"]           = self._extract_images(soup)

        logger.info(
            f"[suumo.jp] Parsed: {listing['title'][:45]!r} | "
            f"{pref} {city} | {listing['price']}万円"
        )
        return listing

    # ── Private helpers ────────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # SUUMO detail h1: "石脇（裾野駅） 2550万円"  — or just the address part
        h1 = soup.select_one("h1")
        if h1:
            text = h1.get_text(strip=True)
            # Strip price suffix if embedded
            text = re.sub(r"\s*\d[\d,]*万円.*$", "", text).strip()
            if text and "SUUMO" not in text and len(text) > 3:
                return text

        # Fallback: <title>【SUUMO】石脇（裾野駅） | …</title>
        t = soup.find("title")
        if t:
            text = re.sub(r"【SUUMO】", "", t.get_text())
            text = re.sub(r"\s*[|\|｜].*$", "", text).strip()
            if text:
                return text
        return None

    def _extract_price(self, soup: BeautifulSoup, page_text: str) -> Optional[int]:
        # Try structured data first (table/dt-dd)
        for sel in [".property_view_note--price", ".dottable-priceline", "[class*='price']"]:
            el = soup.select_one(sel)
            if el:
                m = re.search(r"([\d,]+)万円", el.get_text())
                if m:
                    try:
                        return int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

        # Fallback: first price in page (usually in h1 area)
        m = re.search(r"([\d,]+)万円", page_text)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _extract_location(
        self, soup: BeautifulSoup, page_text: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        # SUUMO has address in meta description and in table
        pref = city = addr = None

        # Try table rows (th/td pairs)
        for tr in soup.select("tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)
            if "所在地" in label:
                p, c, a = self._parse_addr(value)
                pref, city, addr = p or pref, c or city, a or addr
                break

        # Fallback: regex on full text
        if not pref:
            m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])([^\s]{2,10}[市区町村])", page_text)
            if m:
                pref = m.group(1)
                city = m.group(2)

        return pref, city, addr

    def _parse_addr(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        pref = city = None
        m = re.search(r"(北海道|東京都|大阪府|京都府|[^\s]{2,4}[都道府県])", text)
        if m:
            pref = m.group(1)
            rest = text[m.end():].strip()
            cm = re.match(r"([^\s]{2,8}[市区町村郡])", rest)
            if cm:
                city = cm.group(1)
                rest = rest[cm.end():].strip()
            return pref, city, rest or None
        return None, None, None

    def _extract_detail_table(self, soup: BeautifulSoup) -> dict:
        details: dict = {}
        for tr in soup.select("tr"):
            tth = tr.select("th")
            ttd = tr.select("td")
            pairs = list(zip([t.get_text(strip=True) for t in tth],
                             [t.get_text(strip=True) for t in ttd]))
            for label, value in pairs:
                if any(k in label for k in ["建物面積", "床面積"]):
                    details.setdefault("building_area", self._parse_area(value))
                elif any(k in label for k in ["土地面積", "敷地面積"]):
                    details.setdefault("land_area", self._parse_area(value))
                elif any(k in label for k in ["築年", "建築年", "竣工"]):
                    details.setdefault("year_built", self._parse_year(value))
                elif any(k in label for k in ["不動産", "業者", "会社"]):
                    details.setdefault("agency_name", value)
        return details

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [".property_view_note--emphasis", ".js-view-more-hide",
                    ".data_detail_txt", ".section_h1-comment", "article"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 50:
                    return text[:3000]
        return None

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        images: list[str] = []
        # SUUMO property images are in .js-thumbnail or data-original
        for img in soup.select(".js-thumbnail img, .property_view_gallery img, img[data-original]"):
            src = (img.get("data-original") or img.get("src") or "")
            if not src or src in seen:
                continue
            if any(s in src for s in ["icon", "logo", "btn", "arrow", "map", "banner"]):
                continue
            full = urljoin(BASE_URL, src)
            images.append(full)
            seen.add(src)
        return images[:15]

    def _parse_area(self, text: str) -> Optional[float]:
        m = re.search(r"([\d,.]+)\s*m?[²㎡]", text, re.IGNORECASE)
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
        era = {"令和": 2018, "平成": 1988, "昭和": 1925}
        for name, offset in era.items():
            m = re.search(rf"{name}(\d+)年?", text)
            if m:
                return offset + int(m.group(1))
        return None

    def _mark_sold(self, url: str) -> None:
        try:
            client = _db.get_client()
            _db.mark_inactive(client, url)
        except Exception as e:
            logger.warning(f"[suumo.jp] Could not mark inactive: {e}")
