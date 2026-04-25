// Types mirroring Pydantic models from the backend

export interface Listing {
  id: string
  source_url: string
  source_site: string
  title: string | null
  price: number | null          // 万円
  location_prefecture: string | null
  location_city: string | null
  location_address: string | null
  lat: number | null
  lng: number | null
  area_sqm: number | null
  land_area_sqm: number | null
  year_built: number | null
  images: string[] | null
  kominka_score: number | null
  preservation_score: number | null
  score_reason: string | null
  agency_name: string | null
  scraped_at: string | null
  is_active: boolean
}

export interface ListingDetail extends Listing {
  description: string | null
  contact_email: string | null
  contact_phone: string | null
  updated_at: string | null
}

export interface ListingsPage {
  total: number
  offset: number
  limit: number
  items: Listing[]
}

export interface GeoFeatureProperties {
  id: string
  title: string | null
  price: number | null
  kominka_score: number | null
  location_city: string | null
  location_prefecture: string | null
  image: string | null
}

export interface GeoFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: GeoFeatureProperties
}

export interface GeoJSON {
  type: 'FeatureCollection'
  features: GeoFeature[]
}

export interface PrefectureCount {
  prefecture: string
  count: number
}

export interface StatsResponse {
  total_listings: number
  listings_with_score: number
  avg_score: number | null
  by_prefecture: PrefectureCount[]
}

export interface InquiryCreate {
  listing_id?: string
  name: string
  email: string
  phone?: string
  message: string
}

export interface FiltersState {
  prefecture: string
  minPrice: string
  maxPrice: string
  minScore: string
  isNew: boolean
  q: string
}
