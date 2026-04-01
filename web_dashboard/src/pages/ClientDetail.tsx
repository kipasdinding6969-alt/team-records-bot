import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ClientDetail as TClientDetail } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

const CARD: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 10,
  padding: 20,
  marginBottom: 20,
  boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
}

function Field({ label, value, accent }: { label: string; value: string | number | null | undefined; accent?: string }) {
  const { theme } = useTheme()
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: theme.textSecondary, marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: accent || '#2d2a26' }}>{value || '-'}</div>
    </div>
  )
}

export default function ClientDetail() {
  const { theme } = useTheme()
  const { id } = useParams<{ id: string }>()
  const lang = getLang()
  const [client, setClient] = useState<TClientDetail | null>(null)
  const [links, setLinks] = useState<any[]>([])
  const [timeline, setTimeline] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const nav = useNavigate()

  // Note form
  const [noteContent, setNoteContent] = useState('')
  const [noteType, setNoteType] = useState('comment')
  const [noteSaving, setNoteSaving] = useState(false)

  // Link form
  const [showLinkForm, setShowLinkForm] = useState(false)
  const [linkTargetId, setLinkTargetId] = useState('')
  const [linkType, setLinkType] = useState('related')
  const [linkNote, setLinkNote] = useState('')
  const [linkSaving, setLinkSaving] = useState(false)

  const clientId = id ? parseInt(id, 10) : 0

  async function loadAll() {
    if (!clientId) return
    setLoading(true)
    try {
      const [c, l, tl] = await Promise.all([
        api.clientDetail(clientId),
        api.clientLinks(clientId).catch(() => []),
        api.clientTimeline(clientId).catch(() => []),
      ])
      setClient(c)
      setLinks(l)
      setTimeline(tl)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [id])

  async function handleAddNote() {
    if (!noteContent.trim()) return
    setNoteSaving(true)
    try {
      await api.addClientNote(clientId, { content: noteContent.trim(), note_type: noteType })
      setNoteContent('')
      await loadAll()
    } catch { /* silent */ }
    setNoteSaving(false)
  }

  async function handleAddLink() {
    if (!linkTargetId) return
    setLinkSaving(true)
    try {
      await api.createClientLink({
        client_id_a: clientId,
        client_id_b: parseInt(linkTargetId),
        link_type: linkType,
        note: linkNote || undefined,
      })
      setShowLinkForm(false)
      setLinkTargetId('')
      setLinkNote('')
      await loadAll()
    } catch { /* silent */ }
    setLinkSaving(false)
  }

  async function handleRemoveLink(linkId: number) {
    await api.deleteClientLink(linkId).catch(() => null)
    await loadAll()
  }

  if (loading) return <div style={{ color: theme.textSecondary, padding: 20 }}>{t('common.loading', lang)}</div>
  if (error) return <div style={{ color: theme.badgeRed, padding: 20 }}>{error}</div>
  if (!client) return null

  const statusColor = STATUS_COLORS[client.status] || '#7f848e'
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)

  return (
    <div style={{ color: '#2d2a26' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button
          onClick={() => nav(-1)}
          style={{
            background: '#ffffff', border: '1px solid #e2e8f0', color: theme.textSecondary,
            padding: '6px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 13,
          }}
        >
          {t('detail.back', lang)}
        </button>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: '#2d2a26' }}>{client.phone}</h1>
        <span style={{
          padding: '4px 12px', borderRadius: 4,
          background: `${statusColor}25`, color: statusColor,
          fontSize: 13, fontWeight: 600, marginLeft: 8,
        }}>
          {STATUS_LABELS[client.status] || client.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Client info */}
        <div style={CARD}>
          <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {t('detail.info', lang)}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Field label={t('detail.phone', lang)} value={client.phone} accent="#3b82f6" />
            <Field label={t('detail.source', lang)} value={client.source} />
            <Field label={t('detail.frontdesk', lang)} value={client.frontdesk_name} />
            <Field label={t('detail.team', lang)} value={client.team} />
            <Field label={t('detail.total_deposit', lang)} value={totalDeposits > 0 ? `$${totalDeposits.toFixed(2)}` : null} accent="#22c55e" />
            <Field label={t('detail.created', lang)} value={client.created_at ? new Date(client.created_at).toLocaleDateString() : null} />
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {t('detail.milestones', lang)}
            </div>
            {[
              { label: t('detail.contacted_at', lang), val: client.contacted_at },
              { label: t('detail.replied_at', lang), val: client.replied_at },
              { label: t('detail.registered_at', lang), val: client.registered_at },
              { label: t('detail.training_at', lang), val: client.training_at },
              { label: t('detail.first_order_at', lang), val: client.first_order_at },
            ].map(m => m.val && (
              <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #e2e8f025', fontSize: 13 }}>
                <span style={{ color: theme.textSecondary }}>{m.label}</span>
                <span style={{ color: '#2d2a26' }}>{new Date(m.val).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Deposits */}
        <div style={CARD}>
          <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {t('detail.deposits', lang)} ({client.deposits.length})
          </div>
          {client.deposits.length === 0 ? (
            <div style={{ color: theme.textSecondary, fontSize: 13 }}>{t('detail.no_deposits', lang)}</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                  {[t('detail.amount', lang), t('detail.platform', lang), t('detail.date', lang)].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: theme.textSecondary, fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {client.deposits.map(d => (
                  <tr key={d.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 10px', color: '#22c55e', fontWeight: 600 }}>${d.amount.toFixed(2)} {d.currency}</td>
                    <td style={{ padding: '8px 10px', color: theme.textSecondary }}>{d.platform || '-'}</td>
                    <td style={{ padding: '8px 10px', color: theme.textSecondary, fontSize: 12 }}>{d.deposit_date ? new Date(d.deposit_date).toLocaleDateString() : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Linked clients */}
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {t('detail.links', lang)} ({links.length})
          </div>
          <button
            onClick={() => setShowLinkForm(v => !v)}
            style={{
              padding: '5px 14px', background: '#3b82f6', border: 'none', color: '#fff',
              borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
          >
            {t('detail.add_link', lang)}
          </button>
        </div>

        {showLinkForm && (
          <div style={{ background: '#f8fafc', borderRadius: 6, padding: 14, marginBottom: 14, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="number"
              placeholder={t('detail.target_client_id', lang)}
              value={linkTargetId}
              onChange={e => setLinkTargetId(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 13, width: 130, background: '#fff', color: '#2d2a26' }}
            />
            <select
              value={linkType}
              onChange={e => setLinkType(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 13, background: '#fff', color: '#2d2a26' }}
            >
              {['related', 'same_person', 'referral', 'family'].map(lt => (
                <option key={lt} value={lt}>{t(`link_type.${lt}`, lang)}</option>
              ))}
            </select>
            <input
              placeholder={t('detail.link_note', lang)}
              value={linkNote}
              onChange={e => setLinkNote(e.target.value)}
              style={{ padding: '7px 12px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 13, flex: 1, minWidth: 120, background: '#fff', color: '#2d2a26' }}
            />
            <button
              onClick={handleAddLink}
              disabled={linkSaving || !linkTargetId}
              style={{ padding: '7px 16px', background: '#22c55e', border: 'none', color: '#fff', borderRadius: 5, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            >
              {linkSaving ? '...' : t('common.save', lang)}
            </button>
          </div>
        )}

        {links.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 13 }}>{t('detail.no_links', lang)}</div>
        ) : (
          links.map(lnk => {
            const otherId = lnk.client_id_a === clientId ? lnk.client_id_b : lnk.client_id_a
            const otherPhone = lnk.client_id_a === clientId ? lnk.phone_b : lnk.phone_a
            return (
              <div key={lnk.id} style={{ display: 'flex', gap: 12, padding: '8px 0', borderBottom: '1px solid #f1f5f9', fontSize: 13, alignItems: 'center' }}>
                <span
                  style={{ color: '#3b82f6', cursor: 'pointer', fontWeight: 600 }}
                  onClick={() => nav(`/clients/${otherId}`)}
                >
                  #{otherId} {otherPhone}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 3,
                  background: '#3b82f620', color: '#3b82f6', letterSpacing: 0.5,
                }}>
                  {t(`link_type.${lnk.link_type}`, lang)}
                </span>
                {lnk.note && <span style={{ color: theme.textSecondary, flex: 1 }}>{lnk.note}</span>}
                <button
                  onClick={() => handleRemoveLink(lnk.id)}
                  style={{ background: 'transparent', border: '1px solid #f8717166', color: '#f87171', borderRadius: 4, padding: '2px 8px', fontSize: 11, cursor: 'pointer' }}
                >
                  {t('detail.remove_link', lang)}
                </button>
              </div>
            )
          })
        )}
      </div>

      {/* Add note form */}
      <div style={CARD}>
        <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {t('detail.add_note', lang)}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <select
            value={noteType}
            onChange={e => setNoteType(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 5, fontSize: 13, background: '#fff', color: '#2d2a26' }}
          >
            <option value="comment">{t('note_type.comment', lang)}</option>
            <option value="flag">{t('note_type.flag', lang)}</option>
            <option value="link_note">{t('note_type.link_note', lang)}</option>
          </select>
          <textarea
            placeholder={t('detail.note_placeholder', lang)}
            value={noteContent}
            onChange={e => setNoteContent(e.target.value)}
            rows={2}
            style={{
              flex: 1, padding: '8px 12px', border: '1px solid #e2e8f0', borderRadius: 5,
              fontSize: 13, resize: 'vertical', fontFamily: 'inherit', background: '#fff', color: '#2d2a26',
            }}
          />
          <button
            onClick={handleAddNote}
            disabled={noteSaving || !noteContent.trim()}
            style={{
              padding: '8px 18px', background: '#3b82f6', border: 'none', color: '#fff',
              borderRadius: 5, fontSize: 13, fontWeight: 600, cursor: 'pointer', alignSelf: 'flex-end',
            }}
          >
            {noteSaving ? '...' : t('common.save', lang)}
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div style={CARD}>
        <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {t('detail.timeline', lang)} ({timeline.length})
        </div>
        {timeline.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 13 }}>{t('detail.no_notes', lang)}</div>
        ) : (
          <div>
            {timeline.map((n, i) => (
              <div
                key={`${n.timeline_type || 'note'}-${n.id}-${i}`}
                style={{
                  display: 'flex', gap: 14,
                  paddingBottom: i < timeline.length - 1 ? 16 : 0,
                  marginBottom: i < timeline.length - 1 ? 16 : 0,
                  borderBottom: i < timeline.length - 1 ? '1px solid #f1f5f9' : 'none',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20, flexShrink: 0 }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: n.timeline_type === 'link' ? '#3b82f6'
                      : n.note_type === 'status_change' ? '#22c55e'
                      : n.note_type === 'flag' ? '#f59e0b'
                      : '#e2e8f0',
                    border: '2px solid #ffffff', flexShrink: 0,
                  }} />
                  {i < timeline.length - 1 && (
                    <div style={{ flex: 1, width: 1, background: '#e2e8f0', marginTop: 4 }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: theme.textSecondary }}>
                      {n.staff_name || n.author_name || t('detail.system', lang)}
                      {n.timeline_type === 'link' && (
                        <span style={{ marginLeft: 6, fontSize: 10, background: '#3b82f620', color: '#3b82f6', padding: '1px 6px', borderRadius: 3, fontWeight: 600 }}>
                          LINK
                        </span>
                      )}
                      {n.note_type === 'status_change' && n.old_status && n.new_status && (
                        <span style={{ marginLeft: 8 }}>
                          <span style={{ color: STATUS_COLORS[n.old_status] || '#7f848e' }}>
                            {STATUS_LABELS[n.old_status] || n.old_status}
                          </span>
                          <span style={{ color: theme.textSecondary }}> → </span>
                          <span style={{ color: STATUS_COLORS[n.new_status] || '#2d2a26' }}>
                            {STATUS_LABELS[n.new_status] || n.new_status}
                          </span>
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: 11, color: theme.textSecondary }}>
                      {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                    </span>
                  </div>
                  {n.content && (
                    <div style={{ fontSize: 13, color: '#2d2a26', lineHeight: 1.5 }}>{n.content}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
