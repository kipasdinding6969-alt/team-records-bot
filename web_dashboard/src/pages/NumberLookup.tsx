import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'
import { useTheme } from '../ThemeContext'

interface LookupResult {
  found: boolean
  phone?: string
  phone_normalized?: string
  submitter_name?: string
  submitter_staff_id?: number
  source?: string
  submitted_at?: string
  log?: Array<{
    action: string
    actor_name: string
    created_at: string
    details: string | null
  }>
  linked_clients?: Array<{
    id: number
    phone: string
    status: string
    frontdesk_name: string
  }>
}

interface PhoneStats {
  total_registered: number
  duplicates_blocked: number
}

function NoteForm({ clientId, lang }: { clientId: number; lang: any }) {
  const { theme } = useTheme()
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [msgType, setMsgType] = useState<'success' | 'error'>('success')

  async function handleSave() {
    if (!content.trim()) return
    setSaving(true)
    setMsg('')
    try {
      await api.addClientNote(clientId, { content: content.trim(), note_type: 'comment' })
      setContent('')
      setMsg(t('phone.saved', lang))
      setMsgType('success')
    } catch {
      setMsg(t('phone.save_failed', lang))
      setMsgType('error')
    }
    setSaving(false)
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {t('detail.add_note', lang)}
      </div>
      <div style={{ display: 'flex', gap: 12 }}>
        <input
          className="input"
          placeholder={t('detail.note_placeholder', lang)}
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
        />
        <button className="btn-primary" onClick={handleSave} disabled={saving || !content.trim()}>
          {saving ? '...' : t('common.save', lang)}
        </button>
      </div>
      {msg && <div className={`alert ${msgType === 'error' ? 'alert-error' : 'alert-success'}`} style={{ marginTop: 8, marginBottom: 0, padding: '8px 12px', fontSize: 13 }}>{msg}</div>}
    </div>
  )
}

export default function NumberLookup() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()
  const isAdmin = auth?.role === 'owner' || auth?.role === 'admin'

  const [phone, setPhone] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LookupResult | null>(null)
  const [error, setError] = useState('')
  const [stats, setStats] = useState<PhoneStats | null>(null)
  const [overrideMode, setOverrideMode] = useState(false)
  const [overrideSubmitter, setOverrideSubmitter] = useState('')
  const [overrideStaffId, setOverrideStaffId] = useState('')
  const [overrideLoading, setOverrideLoading] = useState(false)
  const [overrideMsg, setOverrideMsg] = useState('')

  useEffect(() => {
    api.phoneRegistryStats().then(setStats).catch(() => null)
  }, [])

  async function handleSearch() {
    if (!phone.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    setOverrideMode(false)
    setOverrideMsg('')
    try {
      const data = await api.phoneRegistryLookup(phone.trim())
      setResult(data)
    } catch (e: any) {
      setError(e.message || t('common.error', lang))
    } finally {
      setLoading(false)
    }
  }

  async function handleOverride() {
    if (!result?.phone || !overrideSubmitter.trim()) return
    setOverrideLoading(true)
    setOverrideMsg('')
    try {
      await api.phoneRegistryOverride(
        result.phone,
        overrideSubmitter.trim(),
        overrideStaffId ? parseInt(overrideStaffId) : undefined
      )
      setOverrideMsg(t('phone.override_saved', lang))
      setOverrideMode(false)
      const refreshed = await api.phoneRegistryLookup(result.phone)
      setResult(refreshed)
    } catch (e: any) {
      setOverrideMsg(e.message || t('phone.override_failed', lang))
    } finally {
      setOverrideLoading(false)
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleString()
  }

  const isOwnedByMe = result?.submitter_staff_id === auth?.staff_id;

  return (
    <div className="page-container">
      <div style={{ marginBottom: 24 }}>
        <h1 className="page-title">{t('phone.title', lang)}</h1>
        <p className="page-subtitle">{t('phone.description', lang)}</p>
      </div>

      {/* Prominent search bar */}
      <div className="card" style={{ marginBottom: 24, padding: 24 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 20, color: theme.textMuted }}>&#x2315;</span>
            <input
              className="input"
              style={{ fontSize: 16, paddingLeft: 40, height: 48 }}
              placeholder={t('phone.search_placeholder', lang)}
              value={phone}
              onChange={e => setPhone(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              autoFocus
            />
          </div>
          <button className="btn-primary" style={{ height: 48, padding: '0 32px', fontSize: 14 }} onClick={handleSearch} disabled={loading}>
            {loading ? t('phone.searching', lang) : t('common.search', lang)}
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          {error}
        </div>
      )}

      {result !== null && !result.found && (
        <div className="alert alert-success">
          {t('clients.phone_available', lang)}
        </div>
      )}

      {result?.found && (
        <>
          <div className="card" style={{
            marginBottom: 20,
            border: `2px solid ${isOwnedByMe ? theme.success : theme.danger}`,
            background: isOwnedByMe ? theme.successBg : theme.dangerBg,
            boxShadow: `0 8px 24px -4px ${isOwnedByMe ? theme.success : theme.danger}20`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: isOwnedByMe ? theme.success : theme.danger }}>
                {isOwnedByMe ? t('phone.owned_self', lang) : t('phone.owned_other', lang)}
              </div>
              <span className={isOwnedByMe ? 'badge-success' : 'badge-danger'} style={{ fontSize: 13, fontWeight: 600, padding: '4px 12px' }}>
                {isOwnedByMe ? t('phone.editable', lang) : t('phone.locked', lang)}
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20, marginBottom: 12 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="field-label" style={{ color: isOwnedByMe ? theme.success : theme.danger }}>{t('phone.owner', lang)}</span>
                <span style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>{result.submitter_name}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="field-label" style={{ color: isOwnedByMe ? theme.success : theme.danger }}>{t('clients.phone', lang)}</span>
                <span style={{ fontSize: 14, fontWeight: 500, color: theme.textPrimary }}>{result.phone}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="field-label" style={{ color: isOwnedByMe ? theme.success : theme.danger }}>{t('phone.normalized', lang)}</span>
                <span style={{ fontSize: 14, fontWeight: 500, color: theme.textPrimary }}>{result.phone_normalized}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="field-label" style={{ color: isOwnedByMe ? theme.success : theme.danger }}>{t('clients.source', lang)}</span>
                <span style={{ fontSize: 14, fontWeight: 500, color: theme.textPrimary }}>{result.source}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="field-label" style={{ color: isOwnedByMe ? theme.success : theme.danger }}>{t('phone.registered_on', lang)}</span>
                <span style={{ fontSize: 14, fontWeight: 500, color: theme.textPrimary }}>{result.submitted_at ? formatDate(result.submitted_at) : '—'}</span>
              </div>
            </div>

            {isAdmin && (
              <div style={{ marginTop: 24, paddingTop: 20, borderTop: `1px solid ${isOwnedByMe ? theme.success : theme.danger}30`, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                {!overrideMode ? (
                  <button className="btn-secondary" style={{ borderColor: isOwnedByMe ? theme.success : theme.danger, color: isOwnedByMe ? theme.success : theme.danger }} onClick={() => setOverrideMode(true)}>
                    {t('phone.admin_override', lang)}
                  </button>
                ) : (
                  <div className="card" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', width: '100%', padding: 20 }}>
                    <input
                      className="input"
                      style={{ flex: 1, minWidth: 200 }}
                      placeholder={t("phone.new_owner", lang)}
                      value={overrideSubmitter}
                      onChange={e => setOverrideSubmitter(e.target.value)}
                    />
                    <input
                      className="input"
                      style={{ width: 140 }}
                      placeholder={t("phone.staff_id_opt", lang)}
                      value={overrideStaffId}
                      onChange={e => setOverrideStaffId(e.target.value)}
                      type="number"
                    />
                    <button className="btn-primary" onClick={handleOverride} disabled={overrideLoading}>
                      {overrideLoading ? t('common.saving', lang) : t('common.confirm', lang)}
                    </button>
                    <button className="btn-secondary" onClick={() => { setOverrideMode(false); setOverrideMsg('') }}>
                      {t('common.cancel', lang)}
                    </button>
                  </div>
                )}
                {overrideMsg && (
                  <span style={{ fontSize: 13, fontWeight: 600, color: overrideMsg.includes('failed') ? theme.danger : theme.success }}>
                    {overrideMsg}
                  </span>
                )}
              </div>
            )}
          </div>

          {result.linked_clients && result.linked_clients.length > 0 && (
            <NoteForm clientId={result.linked_clients[0].id} lang={lang} />
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 20 }}>
            {result.linked_clients !== undefined && (
              <div className="card">
                <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {t('phone.linked_clients', lang)} <span style={{ color: theme.textMuted, fontWeight: 400 }}>({result.linked_clients.length})</span>
                </div>
                {result.linked_clients.length === 0 ? (
                  <div className="empty-state" style={{ padding: 20 }}>
                    <div style={{ fontSize: 32, opacity: 0.5, marginBottom: 8 }}></div>
                    <div>{t('phone.no_linked', lang)}</div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {result.linked_clients.map((c: any, i: number) => (
                      <div key={i} style={{ display: 'flex', gap: 12, padding: '12px 0', borderBottom: i === result.linked_clients!.length - 1 ? 'none' : `1px solid ${theme.cardBorder}`, fontSize: 14, alignItems: 'center' }}>
                        <a
                          href={`/clients/${c.id}`}
                          className="pill-badge" style={{ color: theme.accent, fontWeight: 600, textDecoration: 'none', background: theme.accentLight }}
                        >
                          #{c.id}
                        </a>
                        <span style={{ fontWeight: 600, color: theme.textPrimary }}>{c.phone}</span>
                        <span style={{ color: theme.textSecondary, fontSize: 13 }}>{c.status}</span>
                        {c.frontdesk_name && (
                          <span className="pill-badge" style={{ marginLeft: 'auto', background: theme.bg, border: `1px solid ${theme.cardBorder}`, color: theme.textSecondary, fontSize: 12 }}>
                            {c.frontdesk_name}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {result.log && result.log.length > 0 && (
              <div className="card" style={{ overflow: 'hidden' }}>
                <div className="section-title">{t('phone.history', lang)}</div>
                <table className="data-grid-table">
                  <tbody>
                    {result.log.map((entry, i) => (
                      <tr key={i}>
                        <td>
                          <span className="badge-info" style={{ fontSize: 12, fontWeight: 700, padding: '4px 8px', textTransform: 'uppercase', letterSpacing: 0.5 }}>{entry.action}</span>
                        </td>
                        <td style={{ width: '100%' }}>
                          <div style={{ color: theme.textPrimary, fontWeight: 500 }}>{entry.actor_name}</div>
                          {entry.details && (
                            <div style={{ color: theme.textSecondary, fontSize: 13, marginTop: 4 }}>{entry.details}</div>
                          )}
                        </td>
                        <td style={{ color: theme.textMuted, fontSize: 12, whiteSpace: 'nowrap', textAlign: 'right' }}>
                          {formatDate(entry.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {stats && !result?.found && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="section-title">{t('phone.stats', lang)}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div className="metric-card">
              <div className="metric-label">{t('phone.total_numbers', lang)}</div>
              <div className="metric-value" style={{ color: theme.textPrimary }}>{stats.total_registered.toLocaleString() ?? 0}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">{t('phone.duplicates_blocked', lang)}</div>
              <div className="metric-value" style={{ color: theme.textPrimary }}>{stats.duplicates_blocked.toLocaleString() ?? 0}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
