"""
run_scraper.py — Entry point for the GitHub Actions scrape job.
Orchestrates: scrape → geocode → score → upsert to Supabase.

Active scrapers:
  - kominka.net   (全国古民家専門サイト)
  - smout.jp      (地方移住・古民家・空き家)

Inactive / DNS-dead sites (checked 2026-04):
  - shizuoka-akiya.net  → DNS failure
  - akiya.pref.shizuoka.jp → DNS failure
  - chiba-iju.jp         → DNS failure
  - yamanashi-iju.jp     → DNS failure
  - fujiyoshida-akiya.jp → DNS failure
  - fujinomiya-akiya.jp  → DNS failure
  - tateyama-akiyabank.jp → DNS failure
  - akiya.maruchiba.jp   → DNS failure
  - akiya-athome.jp      → JS-only, no static listing index
"""

import os
import sys
from loguru import logger

from db import get_client, upsert_listing, get_unscored_listings, get_existing_urls
from db import start_scrape_log, finish_scrape_log
from geocoder import geocode_listing
from scorer import score_batch
from scraper_kominka_net import KominkaNetScraper
from scraper_smout import SmoutScraper
from scraper_suumo import SuumoScraper

# ── Logging setup ──────────────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
)


def run_scraper(scraper_class, db_client) -> tuple[int, int, int, int]:
    """
    Run a single scraper end-to-end.
    Returns (found, new, updated, errors).
    """
    source_site = scraper_class.SOURCE_SITE
    found = new = updated = errors = 0

    # Fetch existing URLs to skip duplicates
    existing_urls = get_existing_urls(db_client, source_site)
    logger.info(f"[{source_site}] {len(existing_urls)} existing URLs in DB")

    with scraper_class() as scraper:
        listings = scraper.run()
        found = len(listings)

        for listing in listings:
            # Skip if URL already exists and not needing update
            if listing.get("source_url") in existing_urls:
                logger.debug(f"Already exists, skipping: {listing['source_url']}")
                continue

            try:
                # Geocode (fills lat/lng)
                listing = geocode_listing(listing)

                # Upsert to DB
                is_new, was_updated = upsert_listing(db_client, listing)
                if is_new:
                    new += 1
                elif was_updated:
                    updated += 1

            except Exception as e:
                logger.error(f"Error upserting {listing.get('source_url')}: {e}")
                errors += 1

    return found, new, updated, errors


def run_scoring(db_client) -> int:
    """Score any listings that haven't been scored yet. Returns count scored."""
    unscored = get_unscored_listings(db_client, limit=50)
    if not unscored:
        logger.info("No unscored listings found")
        return 0

    logger.info(f"Scoring {len(unscored)} listings with Gemini 1.5 Flash...")
    score_batch(unscored, db_client=db_client)
    return len(unscored)


def main():
    logger.info("=== Kominka Finder Scrape Job Starting ===")

    db = get_client()

    # ── Active scrapers ────────────────────────────────────────
    # Add new scrapers here as more sites become available.
    scrapers_to_run = [
        KominkaNetScraper,   # kominka.net  — 全国古民家専門
        SmoutScraper,        # smout.jp     — 地方移住・古民家・空き家
        SuumoScraper,        # suumo.jp     — 静岡・千葉・山梨 古民家検索
    ]

    total_found = total_new = total_updated = total_errors = 0

    for scraper_class in scrapers_to_run:
        log_id = start_scrape_log(db, scraper_class.SOURCE_SITE)
        try:
            found, new, updated, errors = run_scraper(scraper_class, db)
            total_found   += found
            total_new     += new
            total_updated += updated
            total_errors  += errors

            finish_scrape_log(
                db, log_id,
                found=found, new=new, updated=updated, errors=errors,
                status="success" if errors == 0 else "partial",
            )
            logger.info(
                f"[{scraper_class.SOURCE_SITE}] Done → "
                f"found={found} new={new} updated={updated} errors={errors}"
            )
        except Exception as e:
            logger.error(f"Scraper {scraper_class.SOURCE_SITE} failed: {e}")
            finish_scrape_log(
                db, log_id,
                found=0, new=0, updated=0, errors=1,
                error_details=str(e), status="failed"
            )
            total_errors += 1

    # ── Run AI scoring on newly-inserted listings ──────────────
    if "GEMINI_API_KEY" in os.environ:
        scored_count = run_scoring(db)
        logger.info(f"AI scoring complete: {scored_count} listings scored")
    else:
        logger.warning("GEMINI_API_KEY not set — skipping AI scoring")

    logger.info(
        f"=== Job Complete === "
        f"total found={total_found} new={total_new} "
        f"updated={total_updated} errors={total_errors}"
    )

    # Exit non-zero if too many errors (will mark GitHub Actions job as failed)
    if total_errors > total_found * 0.5:   # >50% error rate
        sys.exit(1)


if __name__ == "__main__":
    main()
