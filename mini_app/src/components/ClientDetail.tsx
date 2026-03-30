import { useState, useEffect } from 'react'
import { ClientDetail as ClientDetailType } from '../types'
import { api } from '../api'
import { t, statusLabel } from '../i18n'

const STATUSES = [
  'new', 'contacted', 'replied', 'registered', 'training',
  'withdrew', 'ordered', 'ghosted', 'blocked', 'scheduled', 'dead',
]

interface Props {
  clientId: number
  lang: string
  onClose: () => void
  onUpdated: () => void
  showToast: (msg: string) => void
}

function formatDate(iso?: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

export default function ClientDetail({ clientId, lang, onClose, onUpdated, showToast }: Props) {
  const [detail, setDetail] = useState<ClientDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<'view' | 'status' | 'note'>('view')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [noteText, setNoteText] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.getClient(clientId).then(d => {
      setDetail(d)
      setSelectedStatus(d.status)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [clientId])

  async function handleStatusUpdate() {
    if (!selectedStatus || selectedStatus === detail?.status) return
    setSubmitting(true)
    try {
      await api.updateStatus(clientId, selectedStatus)
      showToast(t('success_updated', lang))
      onUpdated()
      onClose()
    } catch {
      showToast(t('error_update', lang))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleAddNote() {
    if (!noteText.trim()) return
    setSubmitting(true)
    try {
      await api.addNote(clientId, noteText.trim())
      showToast(t('success_updated', lang))
      const updated = await api.getClient(clientId)
      setDetail(updated)
      setNoteText('')
      setMode('view')
    } catch {
      showToast(t('error_update', lang))
    } finally {
      setSubmitting(false)
    }
  }

  function haptic() {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-sheet">
        <div className="modal-handle" />

        {loading ? (
          <div className="loading-container" style={{ height: 200 }}>
            <div className="spinner" />
          </div>
        ) : detail ? (
          <>
            <div className="modal-title">
              <span>{detail.phone}</span>
              <span className={`status-badge status-${detail.status}`}>
                {statusLabel(detail.status, lang)}
              </span>
            </div>

            {/* View mode */}
            {mode === 'view' && (
              <>
                <div className="detail-section">
                  <div className="detail-section-title">{t('detail_title', lang)}</div>
                  {detail.frontdesk_name && (
                    <div className="detail-row">
                      <span className="detail-label">{t('client_frontdesk', lang)}</span>
                      <span>{detail.frontdesk_name}</span>
                    </div>
                  )}
                  {detail.source && (
                    <div className="detail-row">
                      <span className="detail-label">{t('client_source', lang)}</span>
                      <span>{detail.source}</span>
                    </div>
                  )}
                  <div className="detail-row">
                    <span className="detail-label">{t('client_deposited', lang)}</span>
                    <span style={{ color: detail.total_deposited > 0 ? '#ffd700' : undefined }}>
                      {detail.total_deposited > 0 ? `💰 ${detail.total_deposited.toLocaleString()}` : '—'}
                    </span>
                  </div>
                  {detail.registered_at && (
                    <div className="detail-row">
                      <span className="detail-label">注册时间</span>
                      <span>{formatDate(detail.registered_at)}</span>
                    </div>
                  )}
                  {detail.first_order_at && (
                    <div className="detail-row">
                      <span className="detail-label">首单时间</span>
                      <span>{formatDate(detail.first_order_at)}</span>
                    </div>
                  )}
                </div>

                {/* Deposits */}
                {detail.deposits.length > 0 && (
                  <div className="detail-section">
                    <div className="detail-section-title">{t('detail_deposits', lang)}</div>
                    {detail.deposits.map(d => (
                      <div key={d.id} className="deposit-item">
                        <span className="deposit-amount">{d.amount.toLocaleString()} {d.currency}</span>
                        <div className="deposit-meta">
                          <div>{d.platform ?? '—'}</div>
                          <div>{formatDate(d.deposit_date)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Notes */}
                <div className="detail-section">
                  <div className="detail-section-title">{t('detail_notes', lang)}</div>
                  {detail.notes.length === 0 ? (
                    <div style={{ color: 'var(--tg-hint)', fontSize: 13 }}>{t('detail_no_notes', lang)}</div>
                  ) : detail.notes.slice(0, 5).map(n => (
                    <div key={n.id} className="note-item">
                      <div className="note-content">{n.content}</div>
                      <div className="note-meta">
                        {n.staff_name && <span>{n.staff_name} · </span>}
                        {formatDate(n.created_at)}
                        {n.old_status && n.new_status && (
                          <span> · {statusLabel(n.old_status, lang)} → {statusLabel(n.new_status, lang)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                <button className="btn-primary" onClick={() => { haptic(); setMode('status') }}>
                  {t('detail_change_status', lang)}
                </button>
                <button className="btn-secondary" onClick={() => { haptic(); setMode('note') }}>
                  {t('detail_add_note', lang)}
                </button>
              </>
            )}

            {/* Status change mode */}
            {mode === 'status' && (
              <>
                <div className="detail-section-title" style={{ marginBottom: 10 }}>
                  {t('detail_change_status', lang)}
                </div>
                <div className="status-grid">
                  {STATUSES.map(s => (
                    <button
                      key={s}
                      className={`status-btn status-${s} ${selectedStatus === s ? 'selected' : ''}`}
                      onClick={() => { haptic(); setSelectedStatus(s) }}
                    >
                      {statusLabel(s, lang)}
                    </button>
                  ))}
                </div>
                <button
                  className="btn-primary"
                  onClick={handleStatusUpdate}
                  disabled={submitting || selectedStatus === detail.status}
                >
                  {submitting ? t('loading', lang) : t('detail_submit', lang)}
                </button>
                <button className="btn-secondary" onClick={() => setMode('view')}>
                  {t('detail_cancel', lang)}
                </button>
              </>
            )}

            {/* Add note mode */}
            {mode === 'note' && (
              <>
                <div className="detail-section-title" style={{ marginBottom: 10 }}>
                  {t('detail_add_note', lang)}
                </div>
                <textarea
                  className="note-input"
                  placeholder={t('detail_note_placeholder', lang)}
                  value={noteText}
                  onChange={e => setNoteText(e.target.value)}
                  autoFocus
                />
                <button
                  className="btn-primary"
                  onClick={handleAddNote}
                  disabled={submitting || !noteText.trim()}
                >
                  {submitting ? t('loading', lang) : t('detail_submit', lang)}
                </button>
                <button className="btn-secondary" onClick={() => setMode('view')}>
                  {t('detail_cancel', lang)}
                </button>
              </>
            )}
          </>
        ) : (
          <div style={{ color: 'var(--tg-hint)', textAlign: 'center', padding: 32 }}>
            {t('error_load', lang)}
          </div>
        )}
      </div>
    </div>
  )
}
