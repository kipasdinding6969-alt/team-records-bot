import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ClientDetail as TClientDetail } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

const getCard = (theme: any): React.CSSProperties => ({
  background: theme.cardBg,
  border: `1px solid ${theme.cardBorder}`,
  borderRadius: 12,
  padding: 24,
  marginBottom: 24,
  boxShadow: theme.shadow,
})

function Field({ label, value, accent }: { label: string; value: string | number | null | undefined; accent?: string }) {
  const { theme } = useTheme()
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 500, color: accent || theme.textPrimary }}>{value || '—'}</div>
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

  // Linked timeline
  const [linkedTimeline, setLinkedTimeline] = useState<any>(null)
  const [showLinked, setShowLinked] = useState(false)

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

  if (loading) return <div style={{ color: theme.textSecondary, padding: 32, fontSize: 15, fontWeight: 500 }}>{t('common.loading', lang)}...</div>
  if (error) return <div style={{ color: theme.danger, padding: 32, fontSize: 15, fontWeight: 500 }}>⚠️ {error}</div>
  if (!client) return null

  const statusColor = STATUS_COLORS[client.status] || theme.textSecondary
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)

  return (
    <div style={{ color: theme.textPrimary, maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 32 }}>
        <button className="glass-btn"
          onClick={() => nav(-1)}
          style={{
            background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, color: theme.textPrimary,
            padding: '8px 16px', borderRadius: 8, cursor: 'pointer', fontSize: 14, fontWeight: 600,
            boxShadow: theme.shadow, transition: 'all 0.2s',
          }}
        >
          ← {t('detail.back', lang)}
        </button>
        <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0, color: theme.textPrimary, letterSpacing: '-0.02em' }}>{client.phone}</h1>
        <span style={{
          padding: '6px 14px', borderRadius: 20,
          background: `${statusColor}20`, color: statusColor, border: `1px solid ${statusColor}40`,
          fontSize: 13, fontWeight: 700, marginLeft: 8, textTransform: 'uppercase', letterSpacing: 0.5,
        }}>
          {STATUS_LABELS[client.status] || client.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Client info */}
        <div style={getCard(theme)}>
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 20, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
            👤 {t('detail.info', lang)}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Field label={t('detail.phone', lang)} value={client.phone} accent={theme.accent} />
            <Field label={t('detail.source', lang)} value={client.source} />
            <Field label={t('detail.frontdesk', lang)} value={client.frontdesk_name} />
            <Field label={t('detail.team', lang)} value={client.team} />
            <Field label={t('detail.total_deposit', lang)} value={totalDeposits > 0 ? `$${totalDeposits.toFixed(2)}` : null} accent={theme.success} />
            <Field label={t('detail.created', lang)} value={client.created_at ? new Date(client.created_at).toLocaleDateString() : null} />
          </div>

          <div style={{ marginTop: 24, paddingTop: 20, borderTop: `1px solid ${theme.cardBorder}` }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: theme.textSecondary, marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              🚩 {t('detail.milestones', lang)}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: t('detail.contacted_at', lang), val: client.contacted_at },
                { label: t('detail.replied_at', lang), val: client.replied_at },
                { label: t('detail.registered_at', lang), val: client.registered_at },
                { label: t('detail.training_at', lang), val: client.training_at },
                { label: t('detail.first_order_at', lang), val: client.first_order_at },
              ].map(m => m.val && (
                <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 14, background: theme.bg, padding: '10px 16px', borderRadius: 8 }}>
                  <span style={{ color: theme.textSecondary, fontWeight: 500 }}>{m.label}</span>
                  <span style={{ color: theme.textPrimary, fontWeight: 600 }}>{new Date(m.val).toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Deposits */}
        <div style={getCard(theme)}>
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 20, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
            💰 {t('detail.deposits', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({client.deposits.length})</span>
          </div>
          {client.deposits.length === 0 ? (
            <div style={{ color: theme.textSecondary, fontSize: 14, padding: '16px 0' }}>{t('detail.no_deposits', lang)}</div>
          ) : (
            <div style={{ overflow: 'hidden', borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead style={{ background: theme.bg }}>
                  <tr className="glass-table-row" style={{ borderBottom: `1px solid ${theme.cardBorder}` }}>
                    {[t('detail.amount', lang), t('detail.platform', lang), t('detail.date', lang)].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', color: theme.textSecondary, fontWeight: 600, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {client.deposits.map((d, i) => (
                    <tr className="glass-table-row" key={d.id} style={{ borderBottom: i === client.deposits.length - 1 ? 'none' : `1px solid ${theme.cardBorder}` }}>
                      <td style={{ padding: '12px 16px', color: theme.success, fontWeight: 600 }}>${d.amount.toFixed(2)} {d.currency}</td>
                      <td style={{ padding: '12px 16px', color: theme.textPrimary, fontWeight: 500 }}>{d.platform || '—'}</td>
                      <td style={{ padding: '12px 16px', color: theme.textSecondary, fontSize: 13 }}>{d.deposit_date ? new Date(d.deposit_date).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Linked clients */}
      <div style={getCard(theme)}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
            🔗 {t('detail.links', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({links.length})</span>
          </div>
          <button className="glass-btn"
            onClick={() => setShowLinkForm(v => !v)}
            style={{
              padding: '8px 16px', background: showLinkForm ? theme.cardBorder : theme.accent, border: 'none', color: showLinkForm ? theme.textPrimary : '#fff',
              borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s',
              boxShadow: showLinkForm ? 'none' : theme.shadow,
            }}
          >
            {showLinkForm ? 'Cancel' : `+ ${t('detail.add_link', lang)}`}
          </button>
        </div>

        {showLinkForm && (
          <div style={{ background: theme.bg, borderRadius: 8, border: `1px solid ${theme.cardBorder}`, padding: 20, marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="number"
              placeholder={t('detail.target_client_id', lang)}
              value={linkTargetId}
              onChange={e => setLinkTargetId(e.target.value)}
              style={{ padding: '10px 14px', border: `1px solid ${theme.inputBorder}`, borderRadius: 6, fontSize: 14, width: 160, background: theme.inputBg, color: theme.textPrimary, boxShadow: theme.shadow }}
            />
            <select
              value={linkType}
              onChange={e => setLinkType(e.target.value)}
              style={{ padding: '10px 14px', border: `1px solid ${theme.inputBorder}`, borderRadius: 6, fontSize: 14, background: theme.inputBg, color: theme.textPrimary, boxShadow: theme.shadow }}
            >
              {['related', 'same_person', 'referral', 'family'].map(lt => (
                <option key={lt} value={lt}>{t(`link_type.${lt}`, lang)}</option>
              ))}
            </select>
            <input
              placeholder={t('detail.link_note', lang)}
              value={linkNote}
              onChange={e => setLinkNote(e.target.value)}
              style={{ padding: '10px 14px', border: `1px solid ${theme.inputBorder}`, borderRadius: 6, fontSize: 14, flex: 1, minWidth: 200, background: theme.inputBg, color: theme.textPrimary, boxShadow: theme.shadow }}
            />
            <button className="glass-btn"
              onClick={handleAddLink}
              disabled={linkSaving || !linkTargetId}
              style={{ padding: '10px 24px', background: theme.success, border: 'none', color: '#fff', borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: 'pointer', boxShadow: theme.shadow }}
            >
              {linkSaving ? 'Saving...' : t('common.save', lang)}
            </button>
          </div>
        )}

        {links.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 14, padding: '16px 0' }}>{t('detail.no_links', lang)}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {links.map(lnk => {
              const otherId = lnk.client_id_a === clientId ? lnk.client_id_b : lnk.client_id_a
              const otherPhone = lnk.client_id_a === clientId ? lnk.phone_b : lnk.phone_a
              return (
                <div key={lnk.id} style={{ display: 'flex', gap: 16, padding: '16px', background: theme.bg, borderRadius: 8, border: `1px solid ${theme.cardBorder}`, fontSize: 14, alignItems: 'center' }}>
                  <div
                    style={{ color: theme.accent, cursor: 'pointer', fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}
                    onClick={() => nav(`/clients/${otherId}`)}
                  >
                    #{otherId} <span style={{ color: theme.textPrimary }}>{otherPhone}</span>
                  </div>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 20,
                    background: theme.warningBg, color: theme.warning, border: `1px solid ${theme.warning}40`, letterSpacing: 0.5, textTransform: 'uppercase'
                  }}>
                    {t(`link_type.${lnk.link_type}`, lang)}
                  </span>
                  <span style={{ color: theme.textSecondary, flex: 1, fontSize: 14 }}>{lnk.note || '—'}</span>
                  <button className="glass-btn"
                    onClick={() => handleRemoveLink(lnk.id)}
                    style={{ background: theme.dangerBg, border: `1px solid ${theme.danger}40`, color: theme.danger, borderRadius: 6, padding: '6px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}
                  >
                    {t('detail.remove_link', lang)}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Add note form */}
      <div style={getCard(theme)}>
        <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
          ✏️ {t('detail.add_note', lang)}
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <select
            value={noteType}
            onChange={e => setNoteType(e.target.value)}
            style={{ padding: '12px 16px', border: `1px solid ${theme.inputBorder}`, borderRadius: 8, fontSize: 14, background: theme.inputBg, color: theme.textPrimary, boxShadow: theme.shadow }}
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
              flex: 1, padding: '12px 16px', border: `1px solid ${theme.inputBorder}`, borderRadius: 8,
              fontSize: 14, resize: 'vertical', fontFamily: 'inherit', background: theme.inputBg, color: theme.textPrimary, boxShadow: theme.shadow
            }}
          />
          <button className="glass-btn"
            onClick={handleAddNote}
            disabled={noteSaving || !noteContent.trim()}
            style={{
              padding: '12px 24px', background: theme.accent, border: 'none', color: '#fff',
              borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', alignSelf: 'flex-start', boxShadow: theme.shadow,
            }}
          >
            {noteSaving ? 'Saving...' : t('common.save', lang)}
          </button>
        </div>
      </div>

      {/* Linked Timeline Toggle */}
      {links.length > 0 && (
        <div style={{ ...getCard(theme), cursor: 'pointer' }} onClick={() => {
          if (!linkedTimeline) {
            api.linkedTimeline(clientId).then(setLinkedTimeline).catch(() => {})
          }
          setShowLinked(!showLinked)
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 12, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {t('detail.linked_timeline', lang)} {linkedTimeline ? `(${linkedTimeline.timeline?.length || 0})` : ''}
            </div>
            <span style={{ fontSize: 12, color: theme.accent }}>{showLinked ? '▲ 收起' : '▼ 展开 / Expand'}</span>
          </div>
          {showLinked && linkedTimeline && (
            <div style={{ marginTop: 14 }}>
              {linkedTimeline.linked_client_ids?.length > 0 && (
                <div style={{ marginBottom: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: theme.textSecondary }}>{t('detail.linked_clients', lang)}:</span>
                  {linkedTimeline.linked_client_ids.map((lid: number) => (
                    <span key={lid} onClick={e => { e.stopPropagation(); nav(`/clients/${lid}`) }}
                      style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 10,
                        background: '#dbeafe', color: '#2563eb', cursor: 'pointer', fontWeight: 600,
                      }}>
                      #{lid}
                    </span>
                  ))}
                </div>
              )}
              {(linkedTimeline.timeline || []).map((item: any, i: number) => (
                <div key={`lt-${i}`} style={{
                  padding: '8px 0', borderBottom: i < linkedTimeline.timeline.length - 1 ? '1px solid #f1f5f9' : 'none',
                  display: 'flex', gap: 10, alignItems: 'flex-start',
                }}>
                  <span style={{
                    fontSize: 9, padding: '2px 5px', borderRadius: 4, fontWeight: 700, flexShrink: 0, marginTop: 2,
                    ...(item.timeline_type === 'deposit' ? { background: '#d1fae5', color: '#059669' }
                      : item.timeline_type === 'link' ? { background: '#e0e7ff', color: '#4f46e5' }
                      : item.client_id !== clientId ? { background: '#fef3c7', color: '#92400e' }
                      : { background: '#f1f5f9', color: '#64748b' }),
                  }}>
                    {item.timeline_type === 'deposit' ? '$' : item.timeline_type === 'link' ? '⇄' : item.client_id !== clientId ? `#${item.client_id}` : '●'}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: theme.textSecondary }}>
                      {item.staff_name || item.author_name || '-'}
                      {item.client_phone && item.client_id !== clientId && (
                        <span style={{ marginLeft: 6, fontSize: 10, color: '#3b82f6' }}>({item.client_phone})</span>
                      )}
                      <span style={{ float: 'right', fontSize: 11 }}>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span>
                    </div>
                    {item.content && <div style={{ fontSize: 13, color: '#2d2a26', marginTop: 2 }}>{item.content}</div>}
                  </div>
                </div>
              ))}
              {(linkedTimeline.timeline || []).length === 0 && (
                <div style={{ color: theme.textSecondary, fontSize: 13 }}>{t('detail.no_notes', lang)}</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Timeline */}
      <div style={{ ...getCard(theme), marginBottom: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: theme.textPrimary, marginBottom: 24, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 8 }}>
          📜 {t('detail.timeline', lang)} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({timeline.length})</span>
        </div>
        {timeline.length === 0 ? (
          <div style={{ color: theme.textSecondary, fontSize: 14, padding: '16px 0' }}>{t('detail.no_notes', lang)}</div>
        ) : (
          <div style={{ paddingLeft: 8 }}>
            {timeline.map((n, i) => (
              <div
                key={`${n.timeline_type || 'note'}-${n.id}-${i}`}
                style={{
                  display: 'flex', gap: 20,
                  paddingBottom: i < timeline.length - 1 ? 24 : 0,
                  marginBottom: i < timeline.length - 1 ? 24 : 0,
                  borderBottom: i < timeline.length - 1 ? `1px solid ${theme.cardBorder}` : 'none',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 24, flexShrink: 0 }}>
                  <div style={{
                    width: 14, height: 14, borderRadius: '50%',
                    background: n.timeline_type === 'link' ? theme.accent
                      : n.note_type === 'status_change' ? theme.success
                      : n.note_type === 'flag' ? theme.warning
                      : theme.textMuted,
                    border: `3px solid ${theme.cardBg}`, flexShrink: 0, zIndex: 1,
                    boxShadow: `0 0 0 1px ${theme.cardBorder}`
                  }} />
                  {i < timeline.length - 1 && (
                    <div style={{ flex: 1, width: 2, background: theme.cardBorder, marginTop: 4, marginBottom: -28 }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, display: 'flex', alignItems: 'center', gap: 8 }}>
                      {n.staff_name || n.author_name || t('detail.system', lang)}
                      {n.timeline_type === 'link' && (
                        <span style={{ fontSize: 10, background: theme.warningBg, color: theme.warning, border: `1px solid ${theme.warning}40`, padding: '2px 8px', borderRadius: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                          LINK
                        </span>
                      )}
                      {n.note_type === 'status_change' && n.old_status && n.new_status && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                          <span style={{ color: STATUS_COLORS[n.old_status] || theme.textSecondary, fontWeight: 600, background: `${STATUS_COLORS[n.old_status] || theme.textSecondary}20`, padding: '2px 8px', borderRadius: 12 }}>
                            {STATUS_LABELS[n.old_status] || n.old_status}
                          </span>
                          <span style={{ color: theme.textMuted }}>→</span>
                          <span style={{ color: STATUS_COLORS[n.new_status] || theme.textPrimary, fontWeight: 600, background: `${STATUS_COLORS[n.new_status] || theme.textSecondary}20`, padding: '2px 8px', borderRadius: 12 }}>
                            {STATUS_LABELS[n.new_status] || n.new_status}
                          </span>
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 500 }}>
                      {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                    </span>
                  </div>
                  {n.content && (
                    <div style={{ fontSize: 14, color: theme.textSecondary, lineHeight: 1.6, background: theme.bg, padding: '12px 16px', borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>{n.content}</div>
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
