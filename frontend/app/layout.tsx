import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '古民家ファインダー — 全国の古民家・空き家物件を一括検索',
  description: '全国の古民家・古家・空き家物件を地図で一括検索。AIスコアリングで価値ある物件を見つけよう。kominka.net 等の優良物件をリアルタイム集計。',
  keywords: ['古民家', '空き家', '古家', '不動産', '地方移住', '古民家 購入', 'kominka'],
  openGraph: {
    title: '古民家ファインダー',
    description: '全国の古民家・空き家物件を地図で一括検索',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;600;700&family=Noto+Sans+JP:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        <link
          rel="stylesheet"
          href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossOrigin=""
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
