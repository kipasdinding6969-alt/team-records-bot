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

const getStyles = (theme: any) => ({
  page: {
    padding: 0,
    color: theme.textPrimary,
    minHeight: '100%',
  } as React.CSSProperties,
  header: {
    marginBottom: 24,
  } as React.CSSProperties,
  title: {
    fontSize: 24,
    fontWeight: 700,
    color: theme.textPrimary,
    margin: 0,
    letterSpacing: '-0.02em',
  } as React.CSSProperties,
  searchRow: {
    display: 'flex',
    gap: 12,
    marginBottom: 32,
    maxWidth: 600,
  } as React.CSSProperties,
  input: {
    flex: 1,
    padding: '12px 16px',
    background: theme.inputBg,
    border: `1px solid ${theme.inputBorder}`,
    color: theme.textPrimary,
    borderRadius: 8,
    fontSize: 15,
    outline: 'none',
    boxShadow: theme.shadow,
    transition: 'all 0.2s',
  } as React.CSSProperties,
  btn: {
    padding: '12px 24px',
    background: theme.accent,
    border: 'none',
    color: '#fff',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    boxShadow: theme.shadow,
    transition: 'all 0.2s',
  } as React.CSSProperties,
  btnSecondary: {
    padding: '10px 20px',
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    color: theme.textPrimary,
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
  } as React.CSSProperties,
  card: {
    background: theme.cardBg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
    boxShadow: theme.shadow,
  } as React.CSSProperties,
  cardTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: theme.textPrimary,
    letterSpacing: '-0.01em',
    marginBottom: 16,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  row: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: 24,
    marginBottom: 12,
  } as React.CSSProperties,
  field: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 6,
  } as React.CSSProperties,
  label: {
    fontSize: 12,
    color: theme.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    fontWeight: 600,
  },
  value: {
    fontSize: 15,
    color: theme.textPrimary,
    fontWeight: 500,
  },
  notFound: {
    background: theme.dangerBg,
    border: `1px solid ${theme.danger}40`,
    borderRadius: 12,
    padding: 24,
    color: theme.danger,
    fontSize: 15,
    fontWeight: 500,
    marginBottom: 24,
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  } as React.CSSProperties,
  logRow: {
    display: 'flex',
    gap: 16,
    padding: '12px 0',
    borderBottom: `1px solid ${theme.cardBorder}`,
    fontSize: 14,
    alignItems: 'center',
  } as React.CSSProperties,
  badge: {
    fontSize: 11,
    fontWeight: 700,
    padding: '4px 8px',
    borderRadius: 6,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
    background: theme.accentLight,
    color: theme.accent,
    flexShrink: 0,
  },
  clientRow: {
    display: 'flex',
    gap: 16,
    padding: '12px 0',
    borderBottom: `1px solid ${theme.cardBorder}`,
    fontSize: 14,
    alignItems: 'center',
  } as React.CSSProperties,
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 20,
  } as React.CSSProperties,
  statCard: {
    background: theme.bg,
    border: `1px solid ${theme.cardBorder}`,
    borderRadius: 10,
    padding: '20px 24px',
  } as React.CSSProperties,
  statValue: {
    fontSize: 32,
    fontWeight: 700,
    color: theme.textPrimary,
    letterSpacing: '-0.02em',
  },
  statLabel: {
    fontSize: 13,
    color: theme.textSecondary,
    marginTop: 4,
    fontWeight: 500,
  },
})

function NoteForm({ clientId, lang }: { clientId: number; lang: any }) {
  const { theme } = useTheme()
  const S = getStyles(theme)
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  async function handleSave() {
    if (!content.trim()) return
    setSaving(true)
    setMsg('')
    try {
      await api.addClientNote(clientId, { content: content.trim(), note_type: 'comment' })
      setContent('')
      setMsg('Saved successfully')
    } catch {
      setMsg('Failed to save')
    }
    setSaving(false)
  }

  return (
    <div style={{ ...S.card, background: theme.bg }}>
      <div style={S.cardTitle}>✏️ {t('detail.add_note', lang)}</div>
      <div style={{ display: 'flex', gap: 12 }}>
        <input
          style={S.input}
          placeholder={t('detail.note_placeholder', lang)}
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
        />
        <button className="glass-btn" style={S.btn} onClick={handleSave} disabled={saving || !content.trim()}>
          {saving ? '...' : t('common.save', lang)}
        </button>
      </div>
      {msg && <div style={{ fontSize: 13, marginTop: 8, fontWeight: 500, color: msg.includes('Failed') ? theme.danger : theme.success }}>{msg}</div>}
    </div>
  )
}

export default function NumberLookup() {
  const { theme } = useTheme()
  const S = getStyles(theme)
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
      setOverrideMsg('Override saved.')
      setOverrideMode(false)
      const refreshed = await api.phoneRegistryLookup(result.phone)
      setResult(refreshed)
    } catch (e: any) {
      setOverrideMsg(e.message || 'Override failed')
    } finally {
      setOverrideLoading(false)
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleString()
  }

  const isOwnedByMe = result?.submitter_staff_id === auth?.staff_id;

  return (
    <div style={S.page}>
      <div style={S.header}>
        <h1 style={S.title}>{t('phone.title', lang)}</h1>
        <p style={{ color: theme.textSecondary, marginTop: 6, fontSize: 15 }}>Check phone number availability and history.</p>
      </div>

      <div style={S.searchRow}>
        <input
          style={{...S.input, fontSize: 16}}
          placeholder="Enter phone number..."
          value={phone}
          onChange={e => setPhone(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          autoFocus
        />
        <button className="glass-btn" style={{...S.btn, fontSize: 15, padding: '0 28px'}} onClick={handleSearch} disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {error && (
        <div style={S.notFound}>⚠️ {error}</div>
      )}

      {result !== null && !result.found && (
        <div style={{ ...S.notFound, background: theme.successBg, border: `1px solid ${theme.success}40`, color: theme.success }}>
          ✨ Number is available! No records found.
        </div>
      )}

      {result?.found && (
        <>
          <div style={{
            ...S.card, 
            border: `2px solid ${isOwnedByMe ? theme.success : theme.danger}`,
            background: isOwnedByMe ? theme.successBg : theme.dangerBg,
            boxShadow: `0 8px 24px -4px ${isOwnedByMe ? theme.success : theme.danger}20`
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: isOwnedByMe ? theme.success : theme.danger, display: 'flex', alignItems: 'center', gap: 8 }}>
                {isOwnedByMe ? '✅ Owned by You' : '🔒 Owned by Someone Else'}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: isOwnedByMe ? theme.success : theme.danger, padding: '4px 12px', background: `${isOwnedByMe ? theme.success : theme.danger}20`, borderRadius: 20 }}>
                {isOwnedByMe ? 'Editable' : 'Locked'}
              </div>
            </div>
            
            <div style={S.row}>
              <div style={S.field}>
                <span style={{...S.label, color: isOwnedByMe ? theme.success : theme.danger, opacity: 0.8}}>Owner</span>
                <span style={{...S.value, color: theme.textPrimary, fontSize: 18, fontWeight: 700}}>{result.submitter_name}</span>
              </div>
              <div style={S.field}>
                <span style={{...S.label, color: isOwnedByMe ? theme.success : theme.danger, opacity: 0.8}}>Phone</span>
                <span style={S.value}>{result.phone}</span>
              </div>
              <div style={S.field}>
                <span style={{...S.label, color: isOwnedByMe ? theme.success : theme.danger, opacity: 0.8}}>Normalized</span>
                <span style={S.value}>{result.phone_normalized}</span>
              </div>
              <div style={S.field}>
                <span style={{...S.label, color: isOwnedByMe ? theme.success : theme.danger, opacity: 0.8}}>Source</span>
                <span style={S.value}>{result.source}</span>
              </div>
              <div style={S.field}>
                <span style={{...S.label, color: isOwnedByMe ? theme.success : theme.danger, opacity: 0.8}}>Registered On</span>
                <span style={S.value}>{result.submitted_at ? formatDate(result.submitted_at) : '—'}</span>
              </div>
            </div>
            
            {isAdmin && (
              <div style={{ marginTop: 24, paddingTop: 20, borderTop: `1px solid ${isOwnedByMe ? theme.success : theme.danger}30`, display: 'flex', gap: 12, alignItems: 'center' }}>
                {!overrideMode ? (
                  <button className="glass-btn" style={{...S.btnSecondary, background: 'transparent', borderColor: isOwnedByMe ? theme.success : theme.danger, color: isOwnedByMe ? theme.success : theme.danger}} onClick={() => setOverrideMode(true)}>
                    Admin Override Owner
                  </button>
                ) : (
                  <div className="glass-card" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', width: '100%', padding: 16, borderRadius: 8 }}>
                    <input
                      style={{ ...S.input, flex: 1, minWidth: 200 }}
                      placeholder="New owner name"
                      value={overrideSubmitter}
                      onChange={e => setOverrideSubmitter(e.target.value)}
                    />
                    <input
                      style={{ ...S.input, width: 140 }}
                      placeholder="Staff ID (opt)"
                      value={overrideStaffId}
                      onChange={e => setOverrideStaffId(e.target.value)}
                      type="number"
                    />
                    <button className="glass-btn" style={S.btn} onClick={handleOverride} disabled={overrideLoading}>
                      {overrideLoading ? 'Saving...' : 'Confirm'}
                    </button>
                    <button className="glass-btn"
                      style={{ ...S.btnSecondary }}
                      onClick={() => { setOverrideMode(false); setOverrideMsg('') }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
                {overrideMsg && (
                  <span style={{ fontSize: 14, fontWeight: 600, color: overrideMsg.includes('failed') ? theme.danger : theme.success }}>
                    {overrideMsg}
                  </span>
                )}
              </div>
            )}
          </div>

          {result.linked_clients && result.linked_clients.length > 0 && (
            <NoteForm clientId={result.linked_clients[0].id} lang={lang} />
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
            {result.linked_clients !== undefined && (
              <div style={{...S.card, marginBottom: 0}}>
                <div style={S.cardTitle}>
                  🔗 {t('phone.linked_clients', lang)} <span style={{ color: theme.textMuted, fontWeight: 400 }}>({result.linked_clients.length})</span>
                </div>
                {result.linked_clients.length === 0 ? (
                  <div className="empty-state" style={{ padding: '24px' }}>
                    <div style={{ fontSize: 32, opacity: 0.5, marginBottom: 8 }}>📭</div>
                    <div>No linked clients found.</div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    {result.linked_clients.map((c: any, i: number) => (
                      <div key={i} style={{...S.clientRow, borderBottom: i === result.linked_clients!.length - 1 ? 'none' : `1px solid ${theme.cardBorder}`}}>
                        <a
                          href={`/clients/${c.id}`}
                          className="pill-badge" style={{ color: theme.accent, fontWeight: 600, textDecoration: 'none', cursor: 'pointer', padding: '4px 12px', background: theme.accentLight,  }}
                        >
                          #{c.id}
                        </a>
                        <span style={{ fontWeight: 600, color: theme.textPrimary }}>
                          {c.phone}
                        </span>
                        <span style={{ color: theme.textSecondary, fontSize: 13 }}>• {c.status}</span>
                        {c.frontdesk_name && (
                          <span style={{
                            background: theme.bg, border: `1px solid ${theme.cardBorder}`, color: theme.textSecondary, padding: '2px 8px',
                            borderRadius: 6, fontSize: 12, fontWeight: 500, marginLeft: 'auto'
                          }}>
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
              <div style={{...S.card, marginBottom: 0}}>
                <div style={S.cardTitle}>📜 {t('phone.history', lang)}</div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {result.log.map((entry, i) => (
                    <div key={i} style={{...S.logRow, borderBottom: i === result.log!.length - 1 ? 'none' : `1px solid ${theme.cardBorder}`}}>
                      <span style={S.badge}>{entry.action}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ color: theme.textPrimary, fontWeight: 500 }}>{entry.actor_name}</div>
                        {entry.details && (
                          <div style={{ color: theme.textSecondary, fontSize: 13, marginTop: 2 }}>{entry.details}</div>
                        )}
                      </div>
                      <span style={{ color: theme.textMuted, fontSize: 12 }}>{formatDate(entry.created_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {stats && !result?.found && (
        <div style={{ ...S.card, marginTop: 16 }}>
          <div style={S.cardTitle}>📊 {t('phone.stats', lang)}</div>
          <div style={S.statsGrid}>
            <div style={S.statCard}>
              <div style={S.statLabel}>{t('phone.total_numbers', lang)}</div>
              <div style={S.statValue}>{stats.total_registered.toLocaleString() ?? 0}</div>
            </div>
            <div style={S.statCard}>
              <div style={S.statLabel}>{t('phone.duplicates_blocked', lang)}</div>
              <div style={S.statValue}>{stats.duplicates_blocked.toLocaleString() ?? 0}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
