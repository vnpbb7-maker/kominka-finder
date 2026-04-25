'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import type { GeoFeatureProperties } from '@/lib/types'
import { fetchMapListings } from '@/lib/api'

interface MapViewProps {
  highlightedId?: string | null
  minScore?: number
  onMarkerClick?: (id: string) => void
}

// Leaflet must be imported client-side only
export default function MapView({ highlightedId, minScore, onMarkerClick }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const markersRef = useRef<any[]>([])
  const [loading, setLoading] = useState(false)

  // Bootstrap Leaflet on mount
  useEffect(() => {
    if (typeof window === 'undefined' || mapRef.current) return

    import('leaflet').then((L) => {
      // Fix default icon paths broken by webpack
      delete (L.Icon.Default.prototype as any)._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      })

      const map = L.map(containerRef.current!, {
        center: [36.2, 138.2],
        zoom: 6,
        zoomControl: true,
      })

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 18,
      }).addTo(map)

      mapRef.current = map

      // Load markers when map moves
      map.on('moveend', () => loadMarkers(map, L))
      loadMarkers(map, L)
    })

    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadMarkers = useCallback(async (map: any, L: any) => {
    setLoading(true)
    try {
      const bounds = map.getBounds()
      const sw = bounds.getSouthWest()
      const ne = bounds.getNorthEast()
      const geo = await fetchMapListings(sw.lat, sw.lng, ne.lat, ne.lng, minScore)

      // Remove old markers
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []

      geo.features.forEach((f) => {
        const [lng, lat] = f.geometry.coordinates
        const p = f.properties as GeoFeatureProperties

        const isHighlighted = p.id === highlightedId
        const scoreColor = getScoreColor(p.kominka_score)

        const icon = L.divIcon({
          className: '',
          html: `<div class="map-marker ${isHighlighted ? 'map-marker--active' : ''}" style="--color:${scoreColor}">${
            p.kominka_score ?? '?'
          }</div>`,
          iconSize: [36, 36],
          iconAnchor: [18, 18],
        })

        const marker = L.marker([lat, lng], { icon }).addTo(map)
        marker.bindPopup(buildPopup(p))
        marker.on('click', () => onMarkerClick?.(p.id))
        markersRef.current.push(marker)
      })
    } catch {
      // silently fail for map tiles
    } finally {
      setLoading(false)
    }
  }, [highlightedId, minScore, onMarkerClick])

  // Re-render markers when highlight changes
  useEffect(() => {
    if (!mapRef.current) return
    import('leaflet').then((L) => loadMarkers(mapRef.current, L))
  }, [highlightedId, loadMarkers])

  return (
    <div className="map-wrapper">
      {loading && <div className="map-loading">読み込み中…</div>}
      <div ref={containerRef} className="map-container" />
    </div>
  )
}

function getScoreColor(score: number | null): string {
  if (score == null) return '#6b7280'
  if (score >= 80) return '#d4a017'
  if (score >= 60) return '#4ade80'
  if (score >= 40) return '#60a5fa'
  return '#f87171'
}

function buildPopup(p: GeoFeatureProperties): string {
  return `
    <div class="map-popup">
      ${p.image ? `<img src="${p.image}" alt="" class="map-popup__img" />` : ''}
      <div class="map-popup__body">
        <strong class="map-popup__title">${p.title ?? '（タイトルなし）'}</strong>
        <p class="map-popup__price">${p.price != null ? `${p.price.toLocaleString()}万円` : '要相談'}</p>
        <p class="map-popup__loc">${p.location_prefecture ?? ''}${p.location_city ? '・' + p.location_city : ''}</p>
        <a href="/listings/${p.id}" class="map-popup__link">詳細を見る →</a>
      </div>
    </div>
  `
}
