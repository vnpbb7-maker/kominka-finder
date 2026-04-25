"""
scraper_base.py — Abstract base class for all Kominka Finder scrapers
Enforces: robots.txt compliance, rate limiting, error handling, structured output.
"""

import time
import urllib.robotparser
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.sync_api import sync_playwright, Page, Browser

MIN_DELAY = 5.0  # seconds between page fetches (configurable per subclass)


class BaseScraper(ABC):
    """
    All scrapers inherit from this class.
    Subclasses must implement: scrape_listing_urls() and parse_listing_page().
    """

    SOURCE_SITE: str = ""         # e.g. "kominka.net"
    BASE_URL: str = ""            # e.g. "https://www.kominka.net"
    REQUEST_DELAY: float = MIN_DELAY

    def __init__(self):
        self._robot_parser = urllib.robotparser.RobotFileParser()
        self._last_fetch_time: float = 0.0
        self._browser: Optional[Browser] = None
        self._playwright = None

        # Load robots.txt once at startup
        robots_url = f"{self.BASE_URL}/robots.txt"
        try:
            self._robot_parser.set_url(robots_url)
            self._robot_parser.read()
            logger.info(f"[{self.SOURCE_SITE}] Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"[{self.SOURCE_SITE}] Could not load robots.txt: {e}. Proceeding with caution.")

    # ── Public API ────────────────────────────────────────────

    def run(self) -> list[dict]:
        """
        Entry point. Returns a list of listing dicts ready for DB insert.
        """
        logger.info(f"[{self.SOURCE_SITE}] Starting scrape run")
        listing_urls = self.scrape_listing_urls()
        logger.info(f"[{self.SOURCE_SITE}] Found {len(listing_urls)} listing URLs")

        results = []
        for url in listing_urls:
            if not self._is_allowed(url):
                logger.warning(f"[{self.SOURCE_SITE}] robots.txt disallows: {url}")
                continue
            try:
                self._rate_limit()
                html = self._fetch_html(url)
                listing = self.parse_listing_page(url, html)
                if listing:
                    listing["source_site"] = self.SOURCE_SITE
                    listing["source_url"] = url
                    results.append(listing)
            except Exception as e:
                logger.error(f"[{self.SOURCE_SITE}] Error parsing {url}: {e}")

        logger.info(f"[{self.SOURCE_SITE}] Scraped {len(results)} listings")
        return results

    # ── Abstract methods ──────────────────────────────────────

    @abstractmethod
    def scrape_listing_urls(self) -> list[str]:
        """
        Crawl the index/search pages and return all detail-page URLs.
        Must respect robots.txt and rate limit internally.
        """
        ...

    @abstractmethod
    def parse_listing_page(self, url: str, html: str) -> Optional[dict]:
        """
        Parse a single listing HTML page.
        Returns a dict matching the listings table schema, or None to skip.
        """
        ...

    # ── Helpers ───────────────────────────────────────────────

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_fetch_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_fetch_time = time.time()

    def _is_allowed(self, url: str) -> bool:
        """Check robots.txt before fetching a URL."""
        return self._robot_parser.can_fetch("*", url)

    def _fetch_html(self, url: str, use_playwright: bool = True) -> str:
        """
        Fetch a page. Uses Playwright by default (handles JS-rendered content).
        Falls back to plain httpx for static pages.
        """
        if use_playwright:
            return self._playwright_fetch(url)
        else:
            return self._httpx_fetch(url)

    def _playwright_fetch(self, url: str) -> str:
        """Use Playwright headless browser to render JS and return page HTML."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

        page: Page = self._browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            return html
        finally:
            page.close()

    def _httpx_fetch(self, url: str) -> str:
        """Plain HTTP fetch without JS rendering."""
        with httpx.Client(
            timeout=15.0,
            headers={
                "User-Agent": (
                    "KominkaFinder/1.0 (+https://github.com/your-org/kominka-finder)"
                )
            },
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def close(self) -> None:
        """Clean up Playwright resources."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
