"""
models.py — Pydantic response / request schemas for the kominka-finder API.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
import uuid
from datetime import datetime


# ── Listing ────────────────────────────────────────────────────────────────────

class ListingBase(BaseModel):
    id: uuid.UUID
    source_url: str
    source_site: str
    title: Optional[str] = None
    price: Optional[int] = None           # 万円
    location_prefecture: Optional[str] = None
    location_city: Optional[str] = None
    location_address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    area_sqm: Optional[float] = None
    land_area_sqm: Optional[float] = None
    year_built: Optional[int] = None
    images: Optional[list[str]] = None
    kominka_score: Optional[int] = None
    preservation_score: Optional[int] = None
    score_reason: Optional[str] = None
    agency_name: Optional[str] = None
    scraped_at: Optional[datetime] = None
    is_active: bool = True


class ListingDetail(ListingBase):
    description: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    updated_at: Optional[datetime] = None


class ListingGeoFeature(BaseModel):
    """Single GeoJSON Feature for map use."""
    type: str = "Feature"
    geometry: dict
    properties: dict


class ListingsGeoJSON(BaseModel):
    type: str = "FeatureCollection"
    features: list[ListingGeoFeature]


class ListingsPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[ListingBase]


# ── Inquiry ────────────────────────────────────────────────────────────────────

class InquiryCreate(BaseModel):
    listing_id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    message: str = Field(..., min_length=10, max_length=2000)


class InquiryResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime


# ── Stats ──────────────────────────────────────────────────────────────────────

class PrefectureCount(BaseModel):
    prefecture: str
    count: int


class StatsResponse(BaseModel):
    total_listings: int
    listings_with_score: int
    avg_score: Optional[float]
    by_prefecture: list[PrefectureCount]
