"""
db.py — Supabase database client wrapper
Handles all read/write operations for the listings table.
"""

import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from supabase import create_client, Client

load_dotenv(Path(__file__).parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


def get_client() -> Client:
    """Return an authenticated Supabase client using the service role key."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_listing(client: Client, listing: dict) -> tuple[bool, bool]:
    """
    Insert or update a listing by source_url.
    Returns (is_new, was_updated) tuple.
    """
    source_url = listing.get("source_url")
    if not source_url:
        raise ValueError("listing must have source_url")

    # Check if it already exists
    existing = (
        client.table("listings")
        .select("id, updated_at")
        .eq("source_url", source_url)
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        # UPDATE existing listing
        record_id = existing.data[0]["id"]
        listing["updated_at"] = now
        # Don't overwrite AI scores if they already exist
        if "kominka_score" in listing and listing["kominka_score"] is None:
            del listing["kominka_score"]
            del listing["preservation_score"]

        client.table("listings").update(listing).eq("id", record_id).execute()
        logger.debug(f"Updated: {source_url}")
        return False, True
    else:
        # INSERT new listing
        listing["id"] = str(uuid4())
        listing["scraped_at"] = now
        listing["updated_at"] = now
        client.table("listings").insert(listing).execute()
        logger.debug(f"Inserted: {source_url}")
        return True, False


def get_unscored_listings(client: Client, limit: int = 50) -> list[dict]:
    """Fetch listings that have no AI score yet."""
    result = (
        client.table("listings")
        .select("id, title, description, location_prefecture, location_city, year_built, area_sqm")
        .is_("kominka_score", "null")
        .eq("is_active", True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def update_scores(client: Client, listing_id: str, scores: dict) -> None:
    """Write AI scores back to a listing row."""
    client.table("listings").update(scores).eq("id", listing_id).execute()


def get_existing_urls(client: Client, source_site: str) -> set[str]:
    """Fetch all known source_urls for a given site to skip duplicates fast."""
    result = (
        client.table("listings")
        .select("source_url")
        .eq("source_site", source_site)
        .execute()
    )
    return {row["source_url"] for row in (result.data or [])}


# ── Scrape log helpers ──────────────────────────────────────

def start_scrape_log(client: Client, source_site: str) -> str:
    """Create a new scrape_log row and return its ID."""
    row = {"id": str(uuid4()), "source_site": source_site, "status": "running"}
    client.table("scrape_logs").insert(row).execute()
    return row["id"]


def finish_scrape_log(
    client: Client,
    log_id: str,
    found: int,
    new: int,
    updated: int,
    errors: int,
    error_details: Optional[str] = None,
    status: str = "success",
) -> None:
    """Update a scrape_log row with final stats."""
    client.table("scrape_logs").update(
        {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "listings_found": found,
            "listings_new": new,
            "listings_updated": updated,
            "errors": errors,
            "error_details": error_details,
            "status": status,
        }
    ).eq("id", log_id).execute()
