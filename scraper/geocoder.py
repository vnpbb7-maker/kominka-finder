"""
geocoder.py — Nominatim geocoder with rate limiting and caching
Converts Japanese address strings to lat/lng coordinates.
Free tier: 1 request/second, requires a valid User-Agent.
"""

import time
from functools import lru_cache
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Required by Nominatim: identify your app
USER_AGENT = "KominkaFinder/1.0 (https://github.com/your-org/kominka-finder)"
REQUEST_DELAY = 1.5  # seconds between Nominatim requests (their limit is 1/s)

_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Enforce minimum delay between Nominatim requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


@lru_cache(maxsize=2048)
@retry(stop=stop_after_attempt(3), wait=wait_fixed(3))
def geocode(address: str, prefecture: Optional[str] = None) -> Optional[tuple[float, float]]:
    """
    Geocode a Japanese address using Nominatim.
    Returns (lat, lng) or None if not found.
    Uses in-memory LRU cache to avoid re-querying the same address.
    """
    _rate_limit()

    # Build query string — prefecture helps narrow results
    query_parts = []
    if address:
        query_parts.append(address)
    if prefecture:
        query_parts.append(prefecture)
    query_parts.append("日本")  # constrain to Japan

    query = ", ".join(query_parts)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "jp",
                    "accept-language": "ja",
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            results = response.json()

        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            logger.debug(f"Geocoded '{query}' → ({lat}, {lng})")
            return lat, lng
        else:
            logger.warning(f"No geocode result for: {query}")
            return None

    except Exception as e:
        logger.error(f"Geocoding error for '{query}': {e}")
        raise  # let tenacity retry


def geocode_listing(listing: dict) -> dict:
    """
    Attempt to geocode a listing dict in place.
    Uses address → city → prefecture as fallback chain.
    """
    if listing.get("lat") and listing.get("lng"):
        return listing  # already geocoded

    address = listing.get("location_address")
    city = listing.get("location_city")
    prefecture = listing.get("location_prefecture")

    result = None

    # Try full address first
    if address:
        result = geocode(address, prefecture)

    # Fall back to city-level
    if result is None and city:
        result = geocode(city, prefecture)

    # Fall back to prefecture only
    if result is None and prefecture:
        result = geocode(prefecture)

    if result:
        listing["lat"], listing["lng"] = result

    return listing
