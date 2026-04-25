'use client'

import { useState } from 'react'
import type { FiltersState } from '@/lib/types'
import { Search, SlidersHorizontal, X } from 'lucide-react'

const PREFECTURES = [
  '北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県',
  '茨城県','栃木県','群馬県','埼玉県','千葉県','東京都','神奈川県',
  '新潟県','富山県','石川県','福井県','山梨県','長野県','岐阜県',
  '静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県',
  '奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県',
  '徳島県','香川県','愛媛県','高知県','福岡県','佐賀県','長崎県',
  '熊本県','大分県','宮崎県','鹿児島県','沖縄県',
]

const DEFAULT_FILTERS: FiltersState = {
  prefecture: '',
  minPrice: '',
  maxPrice: '',
  minScore: '',
  isNew: false,
  q: '',
}

interface FilterPanelProps {
  onFiltersChange: (filters: FiltersState) => void
  totalCount?: number
}

export default function FilterPanel({ onFiltersChange, totalCount }: FilterPanelProps) {
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS)
  const [expanded, setExpanded] = useState(false)

  function update<K extends keyof FiltersState>(key: K, value: FiltersState[K]) {
    const next = { ...filters, [key]: value }
    setFilters(next)
    onFiltersChange(next)
  }

  function reset() {
    setFilters(DEFAULT_FILTERS)
    onFiltersChange(DEFAULT_FILTERS)
  }

  const hasActive =
    filters.prefecture || filters.minPrice || filters.maxPrice ||
    filters.minScore || filters.isNew || filters.q

  return (
    <div className="filter-panel">
      {/* Search bar */}
      <div className="filter-search">
        <Search size={16} className="filter-search__icon" />
        <input
          id="filter-search"
          type="text"
          placeholder="地名・特徴で検索…"
          value={filters.q}
          onChange={(e) => update('q', e.target.value)}
          className="filter-search__input"
        />
        {filters.q && (
          <button onClick={() => update('q', '')} className="filter-search__clear" aria-label="クリア">
            <X size={14} />
          </button>
        )}
      </div>

      {/* Toggle advanced */}
      <div className="filter-bar">
        <button
          onClick={() => setExpanded(!expanded)}
          className={`filter-toggle ${expanded ? 'filter-toggle--active' : ''}`}
          id="filter-toggle-btn"
        >
          <SlidersHorizontal size={14} />
          絞り込み
          {hasActive && <span className="filter-dot" />}
        </button>

        {hasActive && (
          <button onClick={reset} className="filter-reset" id="filter-reset-btn">
            <X size={14} />
            リセット
          </button>
        )}

        {totalCount != null && (
          <span className="filter-count">{totalCount.toLocaleString()}件</span>
        )}
      </div>

      {/* Advanced filters */}
      {expanded && (
        <div className="filter-advanced">
          <div className="filter-row">
            <label className="filter-label" htmlFor="filter-pref">都道府県</label>
            <select
              id="filter-pref"
              value={filters.prefecture}
              onChange={(e) => update('prefecture', e.target.value)}
              className="filter-select"
            >
              <option value="">すべて</option>
              {PREFECTURES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          <div className="filter-row filter-row--inline">
            <div className="filter-group">
              <label className="filter-label" htmlFor="filter-min-price">価格（下限）</label>
              <div className="filter-input-wrap">
                <input
                  id="filter-min-price"
                  type="number"
                  placeholder="0"
                  min={0}
                  value={filters.minPrice}
                  onChange={(e) => update('minPrice', e.target.value)}
                  className="filter-input"
                />
                <span className="filter-unit">万円〜</span>
              </div>
            </div>
            <div className="filter-group">
              <label className="filter-label" htmlFor="filter-max-price">価格（上限）</label>
              <div className="filter-input-wrap">
                <input
                  id="filter-max-price"
                  type="number"
                  placeholder="上限なし"
                  min={0}
                  value={filters.maxPrice}
                  onChange={(e) => update('maxPrice', e.target.value)}
                  className="filter-input"
                />
                <span className="filter-unit">万円</span>
              </div>
            </div>
          </div>

          <div className="filter-row">
            <label className="filter-label" htmlFor="filter-score">最低スコア</label>
            <div className="filter-slider-wrap">
              <input
                id="filter-score"
                type="range"
                min={0}
                max={100}
                step={10}
                value={filters.minScore || 0}
                onChange={(e) => update('minScore', e.target.value === '0' ? '' : e.target.value)}
                className="filter-slider"
              />
              <span className="filter-slider-val">
                {filters.minScore ? `${filters.minScore}以上` : '制限なし'}
              </span>
            </div>
          </div>

          <div className="filter-row">
            <label className="filter-checkbox-label" htmlFor="filter-new">
              <input
                id="filter-new"
                type="checkbox"
                checked={filters.isNew}
                onChange={(e) => update('isNew', e.target.checked)}
                className="filter-checkbox"
              />
              新着のみ（7日以内）
            </label>
          </div>
        </div>
      )}
    </div>
  )
}
