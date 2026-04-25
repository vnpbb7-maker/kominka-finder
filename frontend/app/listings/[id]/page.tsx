import { fetchListing } from '@/lib/api'
import InquiryForm from '@/components/InquiryForm'
import ScoreBadge from '@/components/ScoreBadge'
import Image from 'next/image'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import {
  ArrowLeft, MapPin, Ruler, Calendar, Building2,
  Phone, Mail, ExternalLink
} from 'lucide-react'

interface Props {
  params: { id: string }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const listing = await fetchListing(params.id)
    return {
      title: `${listing.title ?? '古民家物件'} | 古民家ファインダー`,
      description: listing.description?.slice(0, 160) ??
        `${listing.location_prefecture}${listing.location_city ?? ''}の古民家物件。価格: ${listing.price ? `${listing.price}万円` : '要相談'}`,
    }
  } catch {
    return { title: '物件詳細 | 古民家ファインダー' }
  }
}

export default async function ListingDetailPage({ params }: Props) {
  let listing
  try {
    listing = await fetchListing(params.id)
  } catch {
    notFound()
  }

  const images = listing.images ?? []

  function formatPrice(p: number | null): string {
    if (p == null) return '要相談'
    if (p === 0) return '無償譲渡'
    return `${p.toLocaleString()}万円`
  }

  const specItems = [
    { label: '建物面積', value: listing.area_sqm ? `${listing.area_sqm}㎡` : null },
    { label: '土地面積', value: listing.land_area_sqm ? `${listing.land_area_sqm}㎡` : null },
    { label: '築年数', value: listing.year_built ? `${new Date().getFullYear() - listing.year_built}年（${listing.year_built}年築）` : null },
    { label: '都道府県', value: listing.location_prefecture },
    { label: '市区町村', value: listing.location_city },
    { label: '所在地', value: listing.location_address },
    { label: '掲載サイト', value: listing.source_site },
    { label: '担当業者', value: listing.agency_name },
  ].filter((s) => s.value)

  return (
    <>
      <header className="site-header">
        <Link href="/" className="site-header__logo">
          古民家<span>ファインダー</span>
        </Link>
      </header>

      <div className="detail-page">
        {/* Back */}
        <Link href="/" className="detail-back">
          <ArrowLeft size={14} />
          検索結果に戻る
        </Link>

        {/* Title */}
        <div className="detail-header">
          <h1 className="detail-title">{listing.title ?? '（タイトルなし）'}</h1>
          <p className="detail-price">{formatPrice(listing.price)}</p>

          <div className="detail-meta">
            {(listing.location_prefecture || listing.location_city) && (
              <span className="detail-meta-item">
                <MapPin size={13} />
                {listing.location_prefecture}{listing.location_city && `・${listing.location_city}`}
              </span>
            )}
            {listing.area_sqm && (
              <span className="detail-meta-item">
                <Ruler size={13} />
                {listing.area_sqm}㎡
              </span>
            )}
            {listing.year_built && (
              <span className="detail-meta-item">
                <Calendar size={13} />
                築{new Date().getFullYear() - listing.year_built}年
              </span>
            )}
            {listing.source_site && (
              <span className="detail-meta-item">
                <Building2 size={13} />
                {listing.source_site}
              </span>
            )}
          </div>

          {/* AI Score */}
          <div className="detail-score-row">
            <ScoreBadge score={listing.kominka_score} size="lg" showLabel />
            {listing.preservation_score != null && (
              <>
                <span style={{ fontSize: '.72rem', color: 'var(--text-muted)' }}>保存スコア</span>
                <ScoreBadge score={listing.preservation_score} size="md" />
              </>
            )}
          </div>
          {listing.score_reason && (
            <p className="detail-score-reason">「{listing.score_reason}」</p>
          )}
        </div>

        {/* Gallery */}
        {images.length > 0 && (
          <div className="detail-gallery">
            <div className="detail-gallery__main">
              <Image
                src={images[0]}
                alt={listing.title ?? '物件画像'}
                fill
                className="detail-gallery__img"
                unoptimized
                priority
              />
            </div>
            {images.slice(1, 3).map((src, i) => (
              <div key={i} className="detail-gallery__thumb">
                <Image
                  src={src}
                  alt={`物件画像 ${i + 2}`}
                  fill
                  className="detail-gallery__img"
                  unoptimized
                />
              </div>
            ))}
          </div>
        )}

        {/* Description */}
        {listing.description && (
          <section className="detail-section">
            <h2 className="detail-section__title">物件概要</h2>
            <p className="detail-description">{listing.description}</p>
          </section>
        )}

        {/* Specs */}
        {specItems.length > 0 && (
          <section className="detail-section">
            <h2 className="detail-section__title">詳細情報</h2>
            <div className="detail-specs">
              {specItems.map((s) => (
                <div key={s.label} className="detail-spec">
                  <div className="detail-spec__label">{s.label}</div>
                  <div className="detail-spec__value">{s.value}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Contact info */}
        {(listing.contact_phone || listing.contact_email) && (
          <section className="detail-section">
            <h2 className="detail-section__title">問い合わせ先</h2>
            <div className="detail-specs">
              {listing.contact_phone && (
                <div className="detail-spec">
                  <div className="detail-spec__label">電話</div>
                  <div className="detail-spec__value">
                    <a href={`tel:${listing.contact_phone}`} style={{ color: 'var(--gold-light)' }}>
                      {listing.contact_phone}
                    </a>
                  </div>
                </div>
              )}
              {listing.contact_email && (
                <div className="detail-spec">
                  <div className="detail-spec__label">メール</div>
                  <div className="detail-spec__value">
                    <a href={`mailto:${listing.contact_email}`} style={{ color: 'var(--gold-light)' }}>
                      {listing.contact_email}
                    </a>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Source link */}
        <section className="detail-section">
          <h2 className="detail-section__title">掲載元</h2>
          <a
            href={listing.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="detail-source-link"
          >
            <ExternalLink size={14} />
            {listing.source_site ?? '元サイトで見る'}
          </a>
        </section>

        {/* Inquiry form */}
        <section className="detail-section">
          <h2 className="detail-section__title">お問い合わせ</h2>
          <InquiryForm listing={listing} />
        </section>
      </div>
    </>
  )
}
