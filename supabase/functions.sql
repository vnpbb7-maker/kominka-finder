-- ============================================================
-- Kominka Finder — Functions & Additions
-- Run this AFTER schema.sql in Supabase SQL Editor
-- ============================================================

-- ── RPC: Listings within bounding box (for map viewport) ────
CREATE OR REPLACE FUNCTION listings_in_bbox(
  sw_lat float,
  sw_lng float,
  ne_lat float,
  ne_lng float,
  min_score int DEFAULT NULL,
  max_results int DEFAULT 500
)
RETURNS TABLE (
  id uuid,
  title text,
  price integer,
  lat float,
  lng float,
  location_prefecture text,
  location_city text,
  images text[],
  kominka_score integer
)
LANGUAGE sql STABLE
AS $$
  SELECT
    l.id, l.title, l.price, l.lat, l.lng,
    l.location_prefecture, l.location_city,
    l.images, l.kominka_score
  FROM listings l
  WHERE
    l.is_active = true
    AND l.lat IS NOT NULL
    AND l.lng IS NOT NULL
    AND l.lat BETWEEN sw_lat AND ne_lat
    AND l.lng BETWEEN sw_lng AND ne_lng
    AND (min_score IS NULL OR l.kominka_score >= min_score)
  ORDER BY l.kominka_score DESC NULLS LAST
  LIMIT max_results;
$$;

-- Grant execute permission to anon role (public map access)
GRANT EXECUTE ON FUNCTION listings_in_bbox TO anon;
GRANT EXECUTE ON FUNCTION listings_in_bbox TO authenticated;
