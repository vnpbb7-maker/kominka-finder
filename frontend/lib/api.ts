import type {
  ListingsPage,
  ListingDetail,
  GeoJSON,
  StatsResponse,
  InquiryCreate,
  FiltersState,
} from './types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API error ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ── Listings ─────────────────────────────────────────────────────────────────

export function buildListingsQuery(filters: Partial<FiltersState>, page = 0, limit = 20): string {
  const params = new URLSearchParams()
  if (filters.prefecture) params.set('prefecture', filters.prefecture)
  if (filters.minPrice)   params.set('min_price', filters.minPrice)
  if (filters.maxPrice)   params.set('max_price', filters.maxPrice)
  if (filters.minScore)   params.set('min_score', filters.minScore)
  if (filters.isNew)      params.set('is_new', 'true')
  if (filters.q)          params.set('q', filters.q)
  params.set('limit', String(limit))
  params.set('offset', String(page * limit))
  return params.toString()
}

export async function fetchListings(
  filters: Partial<FiltersState>,
  page = 0,
  limit = 20,
): Promise<ListingsPage> {
  const qs = buildListingsQuery(filters, page, limit)
  return apiFetch<ListingsPage>(`/api/listings?${qs}`)
}

export async function fetchListing(id: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/api/listings/${id}`)
}

export async function fetchMapListings(
  swLat: number, swLng: number, neLat: number, neLng: number,
  minScore?: number,
): Promise<GeoJSON> {
  const params = new URLSearchParams({
    sw_lat: String(swLat),
    sw_lng: String(swLng),
    ne_lat: String(neLat),
    ne_lng: String(neLng),
  })
  if (minScore != null) params.set('min_score', String(minScore))
  return apiFetch<GeoJSON>(`/api/listings/map?${params}`)
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export async function fetchStats(): Promise<StatsResponse> {
  return apiFetch<StatsResponse>('/api/stats')
}

// ── Inquiries ─────────────────────────────────────────────────────────────────

export async function submitInquiry(body: InquiryCreate): Promise<{ id: string }> {
  return apiFetch<{ id: string }>('/api/inquiries', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
