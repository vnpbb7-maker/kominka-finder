'use client'

import { useState, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import { fetchListings, fetchStats } from '@/lib/api'
import type { Listing, FiltersState, StatsResponse } from '@/lib/types'
import ListingCard from '@/components/ListingCard'
import FilterPanel from '@/components/FilterPanel'
import { Building2, TrendingUp, Star, ChevronLeft, ChevronRight } from 'lucide-react'

// Leaflet must be loaded client-side only
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false })

const DEFAULT_FILTERS: FiltersState = {
  prefecture: '',
  minPrice: '',
  maxPrice: '',
  minScore: '',
  isNew: false,
  q: '',
}

const LIMIT = 20

export default function HomePage() {
  const [listings, setListings] = useState<Listing[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)

  const loadedOnce = useRef(false)

  // Initial load
  if (!loadedOnce.current) {
    loadedOnce.current = true
    // Fire async on the client — runs once
    fetchListings(DEFAULT_FILTERS, 0, LIMIT)
      .then((d) => { setListings(d.items); setTotal(d.total) })
      .catch(() => setError('物件の読み込みに失敗しました'))
    fetchStats()
      .then(setStats)
      .catch(() => {})
  }

  const load = useCallback(async (f: FiltersState, p: number) => {
    setLoading(true)
    setError(null)
    try {
      const d = await fetchListings(f, p, LIMIT)
      setListings(d.items)
      setTotal(d.total)
    } catch {
      setError('物件の読み込みに失敗しました')
    } finally {
      setLoading(false)
    }
  }, [])

  function handleFiltersChange(f: FiltersState) {
    setFilters(f)
    setPage(0)
    load(f, 0)
  }

  function handlePageChange(delta: number) {
    const next = page + delta
    setPage(next)
    load(filters, next)
  }

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <>
      {/* ── Header ─────────────────────────────────────────── */}
      <header className="site-header">
        <h1 className="site-header__logo">
          古民家<span>ファインダー</span>
        </h1>
        {stats && (
          <div className="site-header__stats">
            <span>
              <Building2 size={12} style={{ display: 'inline', marginRight: 4 }} />
              掲載件数 <strong>{stats.total_listings.toLocaleString()}</strong>件
            </span>
            {stats.avg_score != null && (
              <span>
                <Star size={12} style={{ display: 'inline', marginRight: 4 }} />
                平均スコア <strong>{stats.avg_score}</strong>
              </span>
            )}
            <span>
              <TrendingUp size={12} style={{ display: 'inline', marginRight: 4 }} />
              スコア済 <strong>{stats.listings_with_score}</strong>件
            </span>
          </div>
        )}
      </header>

      {/* ── Main 2-column layout ────────────────────────────── */}
      <div className="main-layout">
        {/* ── Sidebar: Filters + List ──────────────────────── */}
        <aside className="sidebar">
          <div className="sidebar__filters">
            <FilterPanel
              onFiltersChange={handleFiltersChange}
              totalCount={total}
            />
          </div>

          {loading ? (
            <div className="state-loading">読み込み中…</div>
          ) : error ? (
            <div className="state-error">{error}</div>
          ) : listings.length === 0 ? (
            <div className="state-empty">
              <Building2 size={32} />
              条件に合う物件が見つかりませんでした
            </div>
          ) : (
            <div className="sidebar__list">
              {listings.map((listing) => (
                <ListingCard
                  key={listing.id}
                  listing={listing}
                  highlighted={listing.id === highlightedId}
                  onClick={() => setHighlightedId(
                    listing.id === highlightedId ? null : listing.id
                  )}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="sidebar__pagination">
              <button
                className="sidebar__page-btn"
                id="page-prev-btn"
                disabled={page === 0 || loading}
                onClick={() => handlePageChange(-1)}
              >
                <ChevronLeft size={14} style={{ display: 'inline' }} />
                前へ
              </button>
              <span>{page + 1} / {totalPages}</span>
              <button
                className="sidebar__page-btn"
                id="page-next-btn"
                disabled={page >= totalPages - 1 || loading}
                onClick={() => handlePageChange(1)}
              >
                次へ
                <ChevronRight size={14} style={{ display: 'inline' }} />
              </button>
            </div>
          )}
        </aside>

        {/* ── Map ───────────────────────────────────────────── */}
        <main>
          <MapView
            highlightedId={highlightedId}
            minScore={filters.minScore ? parseInt(filters.minScore) : undefined}
            onMarkerClick={(id) => setHighlightedId(id === highlightedId ? null : id)}
          />
        </main>
      </div>
    </>
  )
}
