-- ============================================================
-- Kominka Finder — Supabase Schema
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- Enable PostGIS for geo queries
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- for fuzzy text search

-- ============================================================
-- MAIN LISTINGS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS listings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url      text UNIQUE NOT NULL,
  source_site     text NOT NULL,            -- e.g. 'kominka.net', 'akiya-athome'
  title           text,
  price           integer,                  -- 万円 (NULL = 要相談)
  location_prefecture text,
  location_city   text,
  location_address text,
  lat             float,
  lng             float,
  geom            geometry(Point, 4326),    -- PostGIS point for map queries
  area_sqm        float,
  land_area_sqm   float,
  year_built      integer,
  description     text,
  images          text[],                   -- array of image URLs from source
  kominka_score   integer CHECK (kominka_score BETWEEN 0 AND 100),
  preservation_score integer CHECK (preservation_score BETWEEN 0 AND 100),
  score_reason    text,
  contact_email   text,
  contact_phone   text,
  agency_name     text,
  scraped_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now(),
  is_active       boolean DEFAULT true
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Geo spatial index for map viewport queries
CREATE INDEX IF NOT EXISTS listings_geom_idx
  ON listings USING GIST (geom);

-- Common filter indexes
CREATE INDEX IF NOT EXISTS listings_prefecture_idx
  ON listings (location_prefecture);

CREATE INDEX IF NOT EXISTS listings_price_idx
  ON listings (price);

CREATE INDEX IF NOT EXISTS listings_score_idx
  ON listings (kominka_score DESC);

CREATE INDEX IF NOT EXISTS listings_active_idx
  ON listings (is_active, scraped_at DESC);

-- Full-text search index (Japanese + English)
CREATE INDEX IF NOT EXISTS listings_fts_idx
  ON listings USING GIN (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(location_city, ''))
  );

-- Trigram index for partial text match
CREATE INDEX IF NOT EXISTS listings_title_trgm_idx
  ON listings USING GIN (title gin_trgm_ops);

-- ============================================================
-- AUTO-UPDATE updated_at TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER listings_updated_at
  BEFORE UPDATE ON listings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- AUTO-SYNC geom FROM lat/lng TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION sync_geom_from_latlong()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
    NEW.geom = ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER listings_sync_geom
  BEFORE INSERT OR UPDATE OF lat, lng ON listings
  FOR EACH ROW EXECUTE FUNCTION sync_geom_from_latlong();

-- ============================================================
-- INQUIRY LOG TABLE (for contact form submissions)
-- ============================================================
CREATE TABLE IF NOT EXISTS inquiries (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id   uuid REFERENCES listings(id) ON DELETE SET NULL,
  name         text NOT NULL,
  email        text NOT NULL,
  phone        text,
  message      text NOT NULL,
  sent_to      text,   -- agency email the inquiry was forwarded to
  created_at   timestamptz DEFAULT now()
);

-- ============================================================
-- SCRAPE LOG TABLE (track each scrape run)
-- ============================================================
CREATE TABLE IF NOT EXISTS scrape_logs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_site    text NOT NULL,
  started_at     timestamptz DEFAULT now(),
  finished_at    timestamptz,
  listings_found integer DEFAULT 0,
  listings_new   integer DEFAULT 0,
  listings_updated integer DEFAULT 0,
  errors         integer DEFAULT 0,
  error_details  text,
  status         text DEFAULT 'running' -- 'running' | 'success' | 'failed'
);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Public can read active listings; only service role can write
-- ============================================================
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE inquiries ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_logs ENABLE ROW LEVEL SECURITY;

-- Anyone can SELECT active listings
CREATE POLICY "listings_public_read" ON listings
  FOR SELECT USING (is_active = true);

-- Only service role (backend) can insert/update/delete
CREATE POLICY "listings_service_write" ON listings
  FOR ALL USING (auth.role() = 'service_role');

-- Inquiries: insert-only for anonymous, service_role sees all
CREATE POLICY "inquiries_public_insert" ON inquiries
  FOR INSERT WITH CHECK (true);

CREATE POLICY "inquiries_service_read" ON inquiries
  FOR SELECT USING (auth.role() = 'service_role');

-- ============================================================
-- HELPER VIEW: listings with "is new" flag (7 days)
-- ============================================================
CREATE OR REPLACE VIEW listings_with_meta AS
SELECT
  *,
  (scraped_at > now() - interval '7 days') AS is_new,
  CASE
    WHEN kominka_score >= 80 THEN 'premium'
    WHEN kominka_score >= 60 THEN 'high'
    WHEN kominka_score >= 40 THEN 'medium'
    ELSE 'low'
  END AS score_tier
FROM listings
WHERE is_active = true;
