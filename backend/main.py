"""
main.py — FastAPI application for Kominka Finder.

Endpoints:
  GET  /api/listings        — paginated listing search
  GET  /api/listings/map    — GeoJSON for map viewport
  GET  /api/listings/{id}   — listing detail
  POST /api/inquiries       — submit inquiry
  GET  /api/stats           — aggregate statistics
"""

from __future__ import annotations
from typing import Optional
import uuid

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from database import get_supabase, get_supabase_admin
from models import (
    ListingBase, ListingDetail, ListingsPage, ListingsGeoJSON,
    ListingGeoFeature, InquiryCreate, InquiryResponse, StatsResponse,
    PrefectureCount,
)

# ── App setup ──────────────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="Kominka Finder API",
    description="古民家物件アグリゲーター — REST API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

origins = [o.strip() for o in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok", "service": "kominka-finder-api"}

@app.get("/health", tags=["system"])
def health():
    return {"status": "healthy"}


# ── Listings ───────────────────────────────────────────────────────────────────

@app.get("/api/listings", response_model=ListingsPage, tags=["listings"])
def get_listings(
    prefecture: Optional[str] = Query(None, description="都道府県フィルター"),
    min_price: Optional[int] = Query(None, ge=0, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, ge=0, description="最高価格（万円）"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="最低スコア"),
    is_new: Optional[bool] = Query(None, description="新着のみ（7日以内）"),
    q: Optional[str] = Query(None, min_length=1, max_length=100, description="テキスト検索"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    db = get_supabase()

    # Use the view that adds is_new / score_tier
    query = db.from_("listings_with_meta").select(
        "id, source_url, source_site, title, price, "
        "location_prefecture, location_city, location_address, "
        "lat, lng, area_sqm, land_area_sqm, year_built, images, "
        "kominka_score, preservation_score, score_reason, "
        "agency_name, scraped_at, is_active",
        count="exact",
    )

    if prefecture:
        query = query.eq("location_prefecture", prefecture)
    if min_price is not None:
        query = query.gte("price", min_price)
    if max_price is not None:
        query = query.lte("price", max_price)
    if min_score is not None:
        query = query.gte("kominka_score", min_score)
    if is_new:
        query = query.eq("is_new", True)
    if q:
        # Supabase full-text search via textSearch
        query = query.text_search(
            "title,description,location_city",
            q,
            config="simple",
        )

    query = (
        query
        .order("kominka_score", desc=True, nullsfirst=False)
        .order("scraped_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    result = query.execute()

    return ListingsPage(
        total=result.count or 0,
        offset=offset,
        limit=limit,
        items=result.data or [],
    )


@app.get("/api/listings/map", response_model=ListingsGeoJSON, tags=["listings"])
def get_listings_map(
    sw_lat: float = Query(..., description="南西緯度"),
    sw_lng: float = Query(..., description="南西経度"),
    ne_lat: float = Query(..., description="北東緯度"),
    ne_lng: float = Query(..., description="北東経度"),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    limit: int = Query(500, ge=1, le=2000),
):
    """Return GeoJSON FeatureCollection for listings within the map viewport bbox."""
    db = get_supabase()

    result = db.rpc(
        "listings_in_bbox",
        {
            "sw_lat": sw_lat,
            "sw_lng": sw_lng,
            "ne_lat": ne_lat,
            "ne_lng": ne_lng,
            "min_score": min_score,
            "max_results": limit,
        },
    ).execute()

    features: list[ListingGeoFeature] = []
    for row in result.data or []:
        lat = row.get("lat")
        lng = row.get("lng")
        if lat is None or lng is None:
            continue
        features.append(
            ListingGeoFeature(
                geometry={"type": "Point", "coordinates": [lng, lat]},
                properties={
                    "id": str(row["id"]),
                    "title": row.get("title"),
                    "price": row.get("price"),
                    "kominka_score": row.get("kominka_score"),
                    "location_city": row.get("location_city"),
                    "location_prefecture": row.get("location_prefecture"),
                    "image": (row.get("images") or [None])[0],
                },
            )
        )

    return ListingsGeoJSON(features=features)


@app.get("/api/listings/{listing_id}", response_model=ListingDetail, tags=["listings"])
def get_listing(listing_id: uuid.UUID):
    db = get_supabase()
    result = (
        db.from_("listings")
        .select("*")
        .eq("id", str(listing_id))
        .eq("is_active", True)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    return result.data


# ── Inquiries ──────────────────────────────────────────────────────────────────

@app.post("/api/inquiries", response_model=InquiryResponse, status_code=201, tags=["inquiries"])
def create_inquiry(body: InquiryCreate):
    db = get_supabase_admin()

    payload = body.model_dump(exclude_none=True)
    if "listing_id" in payload:
        payload["listing_id"] = str(payload["listing_id"])

    result = db.from_("inquiries").insert(payload).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="問い合わせの保存に失敗しました")

    row = result.data[0]
    return InquiryResponse(id=row["id"], created_at=row["created_at"])


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=StatsResponse, tags=["stats"])
def get_stats():
    db = get_supabase()

    # Total active listings
    total_res = (
        db.from_("listings")
        .select("id", count="exact")
        .eq("is_active", True)
        .execute()
    )
    total = total_res.count or 0

    # Listings with score
    scored_res = (
        db.from_("listings")
        .select("id", count="exact")
        .eq("is_active", True)
        .not_.is_("kominka_score", "null")
        .execute()
    )
    scored = scored_res.count or 0

    # Average score
    avg_res = (
        db.from_("listings")
        .select("kominka_score")
        .eq("is_active", True)
        .not_.is_("kominka_score", "null")
        .execute()
    )
    scores = [r["kominka_score"] for r in (avg_res.data or []) if r["kominka_score"] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    # By prefecture
    pref_res = (
        db.from_("listings")
        .select("location_prefecture")
        .eq("is_active", True)
        .not_.is_("location_prefecture", "null")
        .execute()
    )
    pref_counts: dict[str, int] = {}
    for row in pref_res.data or []:
        p = row["location_prefecture"]
        pref_counts[p] = pref_counts.get(p, 0) + 1

    by_prefecture = [
        PrefectureCount(prefecture=k, count=v)
        for k, v in sorted(pref_counts.items(), key=lambda x: -x[1])
    ]

    return StatsResponse(
        total_listings=total,
        listings_with_score=scored,
        avg_score=avg_score,
        by_prefecture=by_prefecture,
    )
