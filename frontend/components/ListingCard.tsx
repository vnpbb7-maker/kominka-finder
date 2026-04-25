'use client'

import Image from 'next/image'
import Link from 'next/link'
import type { Listing } from '@/lib/types'
import ScoreBadge from './ScoreBadge'
import { MapPin, Building2, Ruler, Calendar } from 'lucide-react'

interface ListingCardProps {
  listing: Listing
  highlighted?: boolean
  onClick?: () => void
}

function formatPrice(price: number | null): string {
  if (price == null) return '要相談'
  if (price === 0) return '無償'
  return `${price.toLocaleString()}万円`
}

export default function ListingCard({ listing, highlighted, onClick }: ListingCardProps) {
  const thumb = listing.images?.[0] ?? null

  return (
    <Link
      href={`/listings/${listing.id}`}
      className={`listing-card ${highlighted ? 'listing-card--highlighted' : ''}`}
      onClick={onClick}
    >
      {/* Thumbnail */}
      <div className="listing-card__thumb">
        {thumb ? (
          <Image
            src={thumb}
            alt={listing.title ?? '古民家物件'}
            fill
            sizes="(max-width: 768px) 100vw, 280px"
            className="listing-card__img"
            unoptimized
          />
        ) : (
          <div className="listing-card__no-img">
            <Building2 size={32} className="listing-card__no-img-icon" />
          </div>
        )}
        <ScoreBadge score={listing.kominka_score} size="sm" />
        {listing.source_site && (
          <span className="listing-card__source">{listing.source_site}</span>
        )}
      </div>

      {/* Body */}
      <div className="listing-card__body">
        <h3 className="listing-card__title">{listing.title ?? '（タイトルなし）'}</h3>
        <p className="listing-card__price">{formatPrice(listing.price)}</p>

        <div className="listing-card__meta">
          {(listing.location_prefecture || listing.location_city) && (
            <span className="listing-card__meta-item">
              <MapPin size={12} />
              {listing.location_prefecture}{listing.location_city && `・${listing.location_city}`}
            </span>
          )}
          {listing.area_sqm && (
            <span className="listing-card__meta-item">
              <Ruler size={12} />
              {listing.area_sqm}㎡
            </span>
          )}
          {listing.year_built && (
            <span className="listing-card__meta-item">
              <Calendar size={12} />
              築{new Date().getFullYear() - listing.year_built}年
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
