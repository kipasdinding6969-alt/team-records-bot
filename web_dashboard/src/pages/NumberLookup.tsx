import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
import { getLang, t } from '../i18n'

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

const S = {
  page: {
    padding: 0,
    color: '#e0e0e0',
    minHeight: '100%',
  } as React.CSSProperties,
  header: {
    marginBottom: 24,
  } as React.CSSProperties,
  title: {
    fontSize: 22,
    fontWeight: 700,
    color: '#e0e0e0',
    margin: 0,
  } as React.CSSProperties,
  searchRow: {
    display: 'flex',
    gap: 10,
    marginBottom: 24,
  } as React.CSSProperties,
  input: {
    flex: 1,
    padding: '10px 14px',
    background: '#0f3460',
    border: '1px solid #16213e',
    color: '#e0e0e0',
    borderRadius: 6,
    fontSize: 14,
    outline: 'none',
  } as React.CSSProperties,
  btn: {
    padding: '10px 22px',
    background: '#00b894',
    border: 'none',
    color: '#fff',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  } as React.CSSProperties,
  btnSecondary: {
    padding: '8px 18px',
    background: 'transparent',
    border: '1px solid #fdcb6e',
    color: '#fdcb6e',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  } as React.CSSProperties,
  card: {
    background: '#16213e',
    border: '1px solid #0f3460',
    borderRadius: 8,
    padding: 20,
    marginBottom: 16,
  } as React.CSSProperties,
  cardTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: '#7f848e',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginBottom: 14,
  },
  row: {
    display: 'flex',
    gap: 32,
    flexWrap: 'wrap' as const,
    marginBottom: 8,
  } as React.CSSProperties,
  field: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 3,
  } as React.CSSProperties,
  label: {
    fontSize: 11,
    color: '#7f848e',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  value: {
    fontSize: 14,
    color: '#e0e0e0',
    fontWeight: 600,
  },
  notFound: {
    background: '#16213e',
    border: '1px solid #d6303133',
    borderRadius: 8,
    padding: 20,
    color: '#e88',
    fontSize: 14,
    marginBottom: 16,
  } as React.CSSProperties,
  logRow: {
    display: 'flex',
    gap: 12,
    padding: '8px 0',
    borderBottom: '1px solid #0f3460',
    fontSize: 13,
    alignItems: 'flex-start',
  } as React.CSSProperties,
  badge: {
    fontSize: 10,
    fontWeight: 700,
    padding: '2px 7px',
    borderRadius: 3,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
    background: '#00b89433',
    color: '#00b894',
    flexShrink: 0,
  },
  clientRow: {
    display: 'flex',
    gap: 16,
    padding: '8px 0',
    borderBottom: '1px solid #0f3460',
    fontSize: 13,
    alignItems: 'center',
  } as React.CSSProperties,
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 16,
  } as React.CSSProperties,
  statCard: {
    background: '#0f3460',
    borderRadius: 6,
    padding: '14px 18px',
  } as React.CSSProperties,
  statValue: {
    fontSize: 28,
    fontWeight: 700,
    color: '#00b894',
  },
  statLabel: {
    fontSize: 12,
    color: '#7f848e',
    marginTop: 2,
  },
}

function NoteForm({ clientId, lang }: { clientId: number; lang: string }) {
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
      setMsg('Saved')
    } catch {
      setMsg('Failed')
    }
    setSaving(false)
  }

  return (
    <div style={{ ...S.card, background: '#0f3460' }}>
      <div style={S.cardTitle}>{t('detail.add_note', lang)}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          style={{ ...S.input, flex: 1 }}
          placeholder={t('detail.note_placeholder', lang)}
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
        />
        <button style={S.btn} onClick={handleSave} disabled={saving || !content.trim()}>
          {saving ? '...' : t('common.save', lang)}
        </button>
      </div>
      {msg && <div style={{ fontSize: 12, marginTop: 6, color: msg === 'Failed' ? '#e88' : '#00b894' }}>{msg}</div>}
    </div>
  )
}

function addClientNote(clientId: number, data: { content: string; note_type: string }) {
  return api.addClientNote(clientId, data)
}

export default function NumberLookup() {
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

  return (
    <div style={S.page}>
      <div style={S.header}>
        <h1 style={S.title}>{t('phone.title', lang)}</h1>
      </div>

      <div style={S.searchRow}>
        <input
          style={S.input}
          placeholder={t('phone.search_placeholder', lang)}
          value={phone}
          onChange={e => setPhone(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
        />
        <button style={S.btn} onClick={handleSearch} disabled={loading}>
          {loading ? '...' : t('phone.search', lang)}
        </button>
      </div>

      {error && (
        <div style={{ ...S.notFound, marginBottom: 16 }}>{error}</div>
      )}

      {result !== null && !result.found && (
        <div style={S.notFound}>{t('phone.not_found', lang)}</div>
      )}

      {result?.found && (
        <>
          <div style={S.card}>
            <div style={S.cardTitle}>{t('phone.owner', lang)}</div>
            <div style={S.row}>
              <div style={S.field}>
                <span style={S.label}>{t('phone.owner', lang)}</span>
                <span style={S.value}>{result.submitter_name}</span>
              </div>
              <div style={S.field}>
                <span style={S.label}>Phone</span>
                <span style={S.value}>{result.phone}</span>
              </div>
              <div style={S.field}>
                <span style={S.label}>Normalized</span>
                <span style={S.value}>{result.phone_normalized}</span>
              </div>
              <div style={S.field}>
                <span style={S.label}>{t('phone.source', lang)}</span>
                <span style={S.value}>{result.source}</span>
              </div>
              <div style={S.field}>
                <span style={S.label}>{t('phone.submitted_at', lang)}</span>
                <span style={S.value}>{result.submitted_at ? formatDate(result.submitted_at) : '—'}</span>
              </div>
            </div>
            {isAdmin && (
              <div style={{ marginTop: 14, display: 'flex', gap: 10, alignItems: 'center' }}>
                {!overrideMode ? (
                  <button style={S.btnSecondary} onClick={() => setOverrideMode(true)}>
                    {t('phone.override', lang)}
                  </button>
                ) : (
                  <>
                    <input
                      style={{ ...S.input, flex: 'none', width: 180 }}
                      placeholder="New owner name"
                      value={overrideSubmitter}
                      onChange={e => setOverrideSubmitter(e.target.value)}
                    />
                    <input
                      style={{ ...S.input, flex: 'none', width: 120 }}
                      placeholder="Staff ID (optional)"
                      value={overrideStaffId}
                      onChange={e => setOverrideStaffId(e.target.value)}
                      type="number"
                    />
                    <button style={S.btn} onClick={handleOverride} disabled={overrideLoading}>
                      {overrideLoading ? '...' : t('common.save', lang)}
                    </button>
                    <button
                      style={{ ...S.btnSecondary, border: '1px solid #7f848e', color: '#7f848e' }}
                      onClick={() => { setOverrideMode(false); setOverrideMsg('') }}
                    >
                      {t('common.cancel', lang)}
                    </button>
                  </>
                )}
                {overrideMsg && (
                  <span style={{ fontSize: 13, color: overrideMsg.includes('failed') ? '#e88' : '#00b894' }}>
                    {overrideMsg}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Inline note form for linked clients */}
          {result.linked_clients && result.linked_clients.length > 0 && (
            <NoteForm clientId={result.linked_clients[0].id} lang={lang} />
          )}

          {result.log && result.log.length > 0 && (
            <div style={S.card}>
              <div style={S.cardTitle}>{t('phone.history', lang)}</div>
              {result.log.map((entry, i) => (
                <div key={i} style={S.logRow}>
                  <span style={S.badge}>{entry.action}</span>
                  <span style={{ color: '#e0e0e0', flex: 1 }}>{entry.actor_name}</span>
                  <span style={{ color: '#7f848e', fontSize: 12 }}>{formatDate(entry.created_at)}</span>
                  {entry.details && (
                    <span style={{ color: '#7f848e', fontSize: 12 }}>{entry.details}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {result.linked_clients !== undefined && (
            <div style={S.card}>
              <div style={S.cardTitle}>
                {t('phone.linked_clients', lang)} ({result.linked_clients.length})
              </div>
              {result.linked_clients.length === 0 ? (
                <div style={{ color: '#7f848e', fontSize: 13 }}>—</div>
              ) : (
                result.linked_clients.map((c: any, i: number) => (
                  <div key={i} style={S.clientRow}>
                    <a
                      href={`/clients/${c.id}`}
                      style={{ color: '#74b9ff', fontWeight: 600, textDecoration: 'none', cursor: 'pointer' }}
                    >
                      #{c.id}
                    </a>
                    <span style={{
                      background: '#00b89422', color: '#00b894', padding: '2px 8px',
                      borderRadius: 4, fontSize: 11, fontWeight: 600,
                    }}>
                      {c.phone}
                    </span>
                    <span style={{ color: '#7f848e' }}>{c.status}</span>
                    {c.frontdesk_name && (
                      <span style={{
                        background: '#fdcb6e22', color: '#fdcb6e', padding: '2px 8px',
                        borderRadius: 4, fontSize: 11, fontWeight: 600,
                      }}>
                        {c.frontdesk_name}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}

      {stats && (
        <div style={{ ...S.card, marginTop: 8 }}>
          <div style={S.cardTitle}>{t('phone.stats', lang)}</div>
          <div style={S.statsGrid}>
            <div style={S.statCard}>
              <div style={S.statValue}>{stats.total_registered ?? 0}</div>
              <div style={S.statLabel}>{t('phone.total_numbers', lang)}</div>
            </div>
            <div style={S.statCard}>
              <div style={S.statValue}>{stats.duplicates_blocked ?? 0}</div>
              <div style={S.statLabel}>{t('phone.duplicates_blocked', lang)}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
