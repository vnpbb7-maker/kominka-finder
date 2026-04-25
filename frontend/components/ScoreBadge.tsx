'use client'

import clsx from 'clsx'

interface ScoreBadgeProps {
  score: number | null
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
}

function getTier(score: number | null) {
  if (score == null) return { label: '未評価', color: 'badge-none' }
  if (score >= 80)   return { label: 'プレミアム', color: 'badge-premium' }
  if (score >= 60)   return { label: '高評価', color: 'badge-high' }
  if (score >= 40)   return { label: '標準', color: 'badge-medium' }
  return               { label: '要確認', color: 'badge-low' }
}

export default function ScoreBadge({ score, size = 'md', showLabel = false }: ScoreBadgeProps) {
  const { label, color } = getTier(score)
  return (
    <span
      className={clsx('score-badge', color, `score-badge--${size}`)}
      title={label}
    >
      {score != null ? (
        <>
          <span className="score-badge__num">{score}</span>
          {size !== 'sm' && <span className="score-badge__max">/100</span>}
        </>
      ) : (
        '—'
      )}
      {showLabel && <span className="score-badge__label">{label}</span>}
    </span>
  )
}
