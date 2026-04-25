# Kominka Finder 🏯

古民家物件を全国の空き家バンク・不動産サイトから自動収集し、AIスコアリング付きで地図表示するアグリゲーターサイト。

## Architecture

```
GitHub Actions (daily cron)
  └── scraper/ (Python + Playwright)
        ├── scraper_kominka_net.py   ← kominka.net scraper
        ├── geocoder.py              ← Nominatim geocoding
        ├── scorer.py                ← Gemini 1.5 Flash AI scoring
        └── run_scraper.py           ← orchestrator
              ↓ upsert
        Supabase (PostgreSQL + PostGIS)
              ↓ REST API
        FastAPI on Render            ← Phase 2 ✅
              ↓
        Next.js on Vercel            ← Phase 3 ✅
```

## Phase Status
- [x] Phase 1: Scraper + DB schema
- [x] Phase 2: AI Scoring + FastAPI backend
- [x] Phase 3: Frontend (Next.js + Leaflet)
- [ ] Phase 4: Multi-source scrapers

---

## Quick Start

### 1. Supabase セットアップ

1. [supabase.com](https://supabase.com) でプロジェクト作成
2. SQL Editor で以下を順番に実行:
   - `supabase/schema.sql` — テーブル・インデックス・RLS
   - `supabase/functions.sql` — 地図用RPCファンクション
3. **Project URL** と **anon key** / **service_role key** をコピー

### 2. バックエンド（FastAPI）

```bash
cd kominka-finder/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env ファイルを設定
cp .env.example .env
# SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY を記入

# 起動
uvicorn main:app --reload --port 8000
# → http://localhost:8000/docs で APIドキュメント確認
```

#### Render へのデプロイ
1. Render で "New Web Service" → リポジトリを接続
2. Root Directory: `backend`
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment Variables に Supabase キーを設定

### 3. フロントエンド（Next.js）

```bash
cd kominka-finder/frontend
npm install
cp .env.local.example .env.local
# NEXT_PUBLIC_API_URL=https://your-backend.onrender.com  (or http://localhost:8000)

# 開発サーバー起動
npm run dev
# → http://localhost:3000
```

#### Vercel へのデプロイ
1. Vercel で "Import Project" → リポジトリを接続
2. Root Directory: `frontend`
3. Environment Variables:
   - `NEXT_PUBLIC_API_URL=https://your-backend.onrender.com`

### 4. スクレーパー（GitHub Actions）

```bash
cd kominka-finder/scraper
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

python run_scraper.py
```

#### GitHub Secrets（GitHub Actions 自動実行用）
| Secret | 説明 |
|--------|------|
| `SUPABASE_URL` | Supabase プロジェクト URL |
| `SUPABASE_SERVICE_KEY` | service_role キー |
| `GEMINI_API_KEY` | Google Gemini API キー |

---

## API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| GET | `/api/listings` | 物件一覧（フィルター・ページング） |
| GET | `/api/listings/{id}` | 物件詳細 |
| GET | `/api/listings/map` | 地図用GeoJSON（bbox） |
| POST | `/api/inquiries` | 問い合わせ送信 |
| GET | `/api/stats` | 統計情報 |
| GET | `/docs` | Swagger UIドキュメント |

## Legal & Ethics
- Respects `robots.txt` on all sites
- Minimum 5-second delay between requests
- Links back to original source (aggregator model, not copy)
- Display source site name on all listings
