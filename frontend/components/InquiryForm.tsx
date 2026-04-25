'use client'

import { useState } from 'react'
import { submitInquiry } from '@/lib/api'
import type { ListingDetail } from '@/lib/types'
import { Send, CheckCircle, AlertCircle } from 'lucide-react'

interface InquiryFormProps {
  listing: ListingDetail
}

export default function InquiryForm({ listing }: InquiryFormProps) {
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    message: `「${listing.title ?? 'この物件'}」について詳しく教えてください。\n\n`,
  })
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  function update(key: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setStatus('loading')
    setErrorMsg('')
    try {
      await submitInquiry({
        listing_id: listing.id,
        name: form.name,
        email: form.email,
        phone: form.phone || undefined,
        message: form.message,
      })
      setStatus('success')
    } catch (err: any) {
      setStatus('error')
      setErrorMsg(err.message || 'エラーが発生しました')
    }
  }

  if (status === 'success') {
    return (
      <div className="inquiry-success">
        <CheckCircle size={40} className="inquiry-success__icon" />
        <h3 className="inquiry-success__title">お問い合わせを送信しました</h3>
        <p className="inquiry-success__body">
          担当者よりご連絡いたします（営業時間内）。
        </p>
      </div>
    )
  }

  return (
    <form className="inquiry-form" onSubmit={handleSubmit} id="inquiry-form">
      <h3 className="inquiry-form__title">この物件に問い合わせる</h3>

      <div className="inquiry-field">
        <label className="inquiry-label" htmlFor="inq-name">お名前 *</label>
        <input
          id="inq-name"
          type="text"
          required
          value={form.name}
          onChange={(e) => update('name', e.target.value)}
          className="inquiry-input"
          placeholder="山田 太郎"
        />
      </div>

      <div className="inquiry-field">
        <label className="inquiry-label" htmlFor="inq-email">メールアドレス *</label>
        <input
          id="inq-email"
          type="email"
          required
          value={form.email}
          onChange={(e) => update('email', e.target.value)}
          className="inquiry-input"
          placeholder="example@email.com"
        />
      </div>

      <div className="inquiry-field">
        <label className="inquiry-label" htmlFor="inq-phone">電話番号（任意）</label>
        <input
          id="inq-phone"
          type="tel"
          value={form.phone}
          onChange={(e) => update('phone', e.target.value)}
          className="inquiry-input"
          placeholder="090-0000-0000"
        />
      </div>

      <div className="inquiry-field">
        <label className="inquiry-label" htmlFor="inq-message">メッセージ *</label>
        <textarea
          id="inq-message"
          required
          minLength={10}
          rows={5}
          value={form.message}
          onChange={(e) => update('message', e.target.value)}
          className="inquiry-textarea"
        />
      </div>

      {status === 'error' && (
        <div className="inquiry-error">
          <AlertCircle size={16} />
          {errorMsg}
        </div>
      )}

      <button
        type="submit"
        disabled={status === 'loading'}
        className="inquiry-submit"
        id="inquiry-submit-btn"
      >
        <Send size={16} />
        {status === 'loading' ? '送信中…' : '送信する'}
      </button>

      <p className="inquiry-notice">
        ※ 送信内容は物件掲載元の不動産業者に転送されます。
      </p>
    </form>
  )
}
