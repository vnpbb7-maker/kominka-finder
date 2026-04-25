/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.kominka.net' },
      { protocol: 'https', hostname: '**.athome.co.jp' },
      { protocol: 'https', hostname: '**.suumo.jp' },
      { protocol: 'https', hostname: '**.akiya-athome.jp' },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
}

module.exports = nextConfig
