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
import db as _db

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

    # ── Sold-out keywords (text anywhere on the page) ─────────
    # kominka.net uses these phrases for sold/withdrawn listings.
    SOLD_KEYWORDS: list[str] = [
        # Explicit sold/closed notices
        "大切にしていただける方を見つかりました",
        "大切にしていただける方が見つかりました",
        "成約済",
        "ご成約",
        "売却済",
        "売れました",
        "売却しました",
        "掲載終了",
        "募集終了",
        "受付終了",
        "公開終了",
        "商談中",       # under negotiation → treat as unavailable
        "SOLD OUT",
        "Sold Out",
        "sold out",
    ]

    # ── Step 2: Parse a detail page ───────────────────────────

    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        """Parse a kominka.net detail page.

        Returns None (and marks the DB row inactive) if the listing is sold.
        """
        soup = BeautifulSoup(html, "lxml")

        logger.debug(f"[kominka.net] Parsing detail page: {url}")
        logger.debug(f"[kominka.net] Detail HTML preview:\n{html[:1000]}")

        # ── 1. Text-based sold detection ────────────────────
        page_text = soup.get_text()
        for kw in self.SOLD_KEYWORDS:
            if kw in page_text:
                logger.info(f"[kominka.net] SOLD OUT ({kw}): {url}")
                self._mark_sold(url)
                return None

        # ── 2. Image alt-text sold detection ─────────────────
        # kominka.net overlays the text on the card thumbnail *and* as alt
        sold_alt_patterns = [
            "大切にしていただける方",
            "成約",
            "売却済",
            "sold",
            "SOLD",
        ]
        for img in soup.select("img"):
            alt = (img.get("alt") or "").lower()
            src = (img.get("src") or "").lower()
            for pat in sold_alt_patterns:
                if pat.lower() in alt or pat.lower() in src:
                    logger.info(f"[kominka.net] SOLD OUT (image: {pat!r}): {url}")
                    self._mark_sold(url)
                    return None

        # ── Build listing dict ────────────────────────────────
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
        listing["area_sqm"]      = details.get("building_area")
        listing["land_area_sqm"] = details.get("land_area")
        listing["year_built"]    = details.get("year_built")
        listing["agency_name"]   = details.get("agency_name")
        listing["contact_phone"] = details.get("contact_phone")
        listing["contact_email"] = details.get("contact_email")

        listing["description"] = self._extract_description(soup)
        listing["images"]      = self._extract_images(soup)

        logger.info(
            f"[kominka.net] Parsed: {listing['title']!r} | "
            f"{listing['location_prefecture']} | {listing['price']}万円"
        )
        return listing

    def _mark_sold(self, url: str) -> None:
        """Set is_active=False in the DB for a sold listing. No-op if not yet in DB."""
        try:
            client = _db.get_client()
            updated = _db.mark_inactive(client, url)
            if not updated:
                logger.debug(f"[kominka.net] Sold listing not yet in DB (ok to skip): {url}")
        except Exception as e:
            logger.warning(f"[kominka.net] Could not mark inactive in DB: {e}")

    # ── Private helpers ───────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # kominka.net: <title>物件名 – 古民家住まいる</title> is the clean title
        # H1 has a noisy prefix like '206013 [東北] 物件名' so we prefer <title>
        t = soup.find("title")
        if t:
            text = re.sub(r"\s*[\u2013\-|\uff5c]\s*古民家住まいる.*$", "", t.get_text()).strip()
            if text:
                return text

        # Fallback: strip prefix from h1
        for sel in ["h1.entry-title", ".entry-title", "h1"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                # Strip leading '206013 [東北] ' style prefix
                text = re.sub(r"^\d+[^\u3041-\u30ff\u4e00-\u9fff]*", "", text).strip()
                text = re.sub(r"^\[[^\]]+\]\s*", "", text).strip()
                if text and "古民家住まいる" not in text:
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

    # Slug → 都道府県名 マッピング（WordPress カテゴリスラッグ）
    SLUG_TO_PREF: dict[str, str] = {
        "hokkaido": "北海道",
        "aomori": "青森県", "iwate": "岩手県", "miyagi": "宮城県",
        "akita": "秋田県", "yamagata": "山形県", "fukushima": "福島県",
        "ibaraki": "茨城県", "tochigi": "栃木県", "gunma": "群馬県",
        "saitama": "埼玉県", "chiba": "千葉県", "tokyo": "東京都",
        "kanagawa": "神奈川県",
        "niigata": "新潟県", "toyama": "富山県", "ishikawa": "石川県",
        "hukui": "福井県", "fukui": "福井県",
        "yamanashi": "山梨県", "nagano": "長野県", "shizuoka": "静岡県",
        "aichi": "愛知県", "mie": "三重県", "gifu": "岐阜県",
        "shiga": "滋賀県", "kyoto": "京都府", "osaka": "大阪府",
        "hyogo": "兵庫県", "nara": "奈良県", "wakayama": "和歌山県",
        "tottori": "鳥取県", "shimane": "島根県", "okayama": "岡山県",
        "hiroshima": "広島県", "yamaguchi": "山口県",
        "tokushima": "徳島県", "kagawa": "香川県", "ehime": "愛媛県",
        "kochi": "高知県",
        "fukuoka": "福岡県", "saga": "佐賀県", "nagasaki": "長崎県",
        "kumamoto": "熊本県", "oita": "大分県", "miyazaki": "宮崎県",
        "kagoshima": "鹿児島県", "okinawa": "沖縄県",
    }

    def _extract_location(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (prefecture, city, address).

        Primary: WordPress post class contains 'category-{slug}' (e.g. category-yamagata)
        Fallback: parse breadcrumb / entry text for Japanese address patterns.
        """
        pref = city = addr = None

        # 1. Parse WordPress category CSS classes on the post container
        #    e.g. class="... category-sale category-yamagata category-touhoku ..."
        post_el = soup.select_one("[class*='category-']")
        if post_el:
            classes = post_el.get("class", [])
            for cls in classes:
                if cls.startswith("category-"):
                    slug = cls.replace("category-", "")
                    if slug in self.SLUG_TO_PREF:
                        pref = self.SLUG_TO_PREF[slug]
                        break

        # 2. Breadcrumb text fallback
        if not pref:
            for sel in [".breadcrumb", "#breadcrumbs", "nav.breadcrumbs"]:
                el = soup.select_one(sel)
                if el:
                    p, c, a = self._parse_japanese_address(el.get_text())
                    if p:
                        pref, city, addr = p, c, a
                        break

        # 3. Entry content text fallback
        if not pref:
            entry = soup.select_one(".entry-content, .panel-body, article")
            if entry:
                p, c, a = self._parse_japanese_address(entry.get_text())
                if p:
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
