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
    <div className="card mb-20">
      <div className="section-title d-flex align-center gap-8">
        {t('detail.add_note', lang)}
      </div>
      <div className="d-flex gap-12">
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
      {msg && <div className={`alert ${msgType === 'error' ? 'alert-error' : 'alert-success'} mt-8 mb-0 p-8-12 caption`}>{msg}</div>}
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
    api.phoneRegistryStats().then(setStats).catch(() => setError(t('common.error', lang)))
  }, [])

  useEffect(() => { if (error) { const id = setTimeout(() => setError(''), 5000); return () => clearTimeout(id) } }, [error])

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
      <div className="mb-24">
        <h1 className="page-title">{t('phone.title', lang)}</h1>
        <p className="page-subtitle">{t('phone.description', lang)}</p>
      </div>

      {/* Prominent search bar */}
      <div className="card mb-24 p-24">
        <div className="d-flex gap-12 align-center">
          <div className="search-icon-wrapper flex-1">
            <span className="search-icon-prefix">&#x2315;</span>
            <input
              className="input input-lg search-input-padded"
              placeholder={t('phone.search_placeholder', lang)}
              value={phone}
              onChange={e => setPhone(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              autoFocus
            />
          </div>
          <button className="btn-primary btn-lg" onClick={handleSearch} disabled={loading}>
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
          <div className={`card mb-20 lookup-result-card ${isOwnedByMe ? 'owned' : 'locked'}`}>
            <div className="d-flex align-center justify-between mb-20">
              <div className={`heading-sm ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>
                {isOwnedByMe ? t('phone.owned_self', lang) : t('phone.owned_other', lang)}
              </div>
              <span className={`${isOwnedByMe ? 'badge-success' : 'badge-danger'} badge-lg`}>
                {isOwnedByMe ? t('phone.editable', lang) : t('phone.locked', lang)}
              </span>
            </div>

            <div className="grid-auto-200 gap-20 mb-12">
              <div className="d-flex flex-col gap-4">
                <span className={`field-label ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>{t('phone.owner', lang)}</span>
                <span className="heading-sm">{result.submitter_name}</span>
              </div>
              <div className="d-flex flex-col gap-4">
                <span className={`field-label ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>{t('clients.phone', lang)}</span>
                <span className="subtitle text-bold">{result.phone}</span>
              </div>
              <div className="d-flex flex-col gap-4">
                <span className={`field-label ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>{t('phone.normalized', lang)}</span>
                <span className="subtitle text-bold">{result.phone_normalized}</span>
              </div>
              <div className="d-flex flex-col gap-4">
                <span className={`field-label ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>{t('clients.source', lang)}</span>
                <span className="subtitle text-bold">{result.source}</span>
              </div>
              <div className="d-flex flex-col gap-4">
                <span className={`field-label ${isOwnedByMe ? 'text-success' : 'text-danger'}`}>{t('phone.registered_on', lang)}</span>
                <span className="subtitle text-bold">{result.submitted_at ? formatDate(result.submitted_at) : '\u2014'}</span>
              </div>
            </div>

            {isAdmin && (
              <div className={`mt-24 pt-20 border-top-status ${isOwnedByMe ? 'owned' : 'locked'} d-flex gap-12 align-center flex-wrap`}>
                {!overrideMode ? (
                  <button className={`btn-secondary ${isOwnedByMe ? 'btn-outline-success' : 'btn-outline-danger'}`} onClick={() => setOverrideMode(true)}>
                    {t('phone.admin_override', lang)}
                  </button>
                ) : (
                  <div className="card d-flex gap-12 flex-wrap w-full p-20">
                    <input
                      className="input flex-1 min-w-200"
                      placeholder={t("phone.new_owner", lang)}
                      value={overrideSubmitter}
                      onChange={e => setOverrideSubmitter(e.target.value)}
                    />
                    <input
                      className="input w-140"
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
                  <span className={`caption text-bold ${overrideMsg.includes('failed') ? 'text-danger' : 'text-success'}`}>
                    {overrideMsg}
                  </span>
                )}
              </div>
            )}
          </div>

          {result.linked_clients && result.linked_clients.length > 0 && (
            <NoteForm clientId={result.linked_clients[0].id} lang={lang} />
          )}

          <div className="grid-auto-400 gap-20">
            {result.linked_clients !== undefined && (
              <div className="card">
                <div className="section-title d-flex align-center gap-8">
                  {t('phone.linked_clients', lang)} <span className="text-muted text-normal">({result.linked_clients.length})</span>
                </div>
                {result.linked_clients.length === 0 ? (
                  <div className="empty-state p-20">
                    <div className="empty-icon-dim mb-8"></div>
                    <div>{t('phone.no_linked', lang)}</div>
                  </div>
                ) : (
                  <div className="d-flex flex-col">
                    {result.linked_clients.map((c: any, i: number) => (
                      <div key={i} className={`d-flex gap-12 p-12-0 align-center subtitle ${i === result.linked_clients!.length - 1 ? '' : 'border-bottom'}`}>
                        <a
                          href={`/clients/${c.id}`}
                          className="pill-badge text-accent text-bold text-decoration-none bg-accent-light"
                        >
                          #{c.id}
                        </a>
                        <span className="text-bold">{c.phone}</span>
                        <span className="caption">{c.status}</span>
                        {c.frontdesk_name && (
                          <span className="pill-badge ml-auto caption border">
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
              <div className="card overflow-hidden">
                <div className="section-title">{t('phone.history', lang)}</div>
                <table className="data-grid-table">
                  <tbody>
                    {result.log.map((entry, i) => (
                      <tr key={i}>
                        <td>
                          <span className="badge-info badge-sm text-bold text-uppercase">{entry.action}</span>
                        </td>
                        <td className="w-full">
                          <div className="text-bold">{entry.actor_name}</div>
                          {entry.details && (
                            <div className="caption mt-4">{entry.details}</div>
                          )}
                        </td>
                        <td className="text-muted caption text-nowrap text-right">
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
        <div className="card mt-20">
          <div className="section-title">{t('phone.stats', lang)}</div>
          <div className="grid-2col gap-20">
            <div className="metric-card">
              <div className="metric-label">{t('phone.total_numbers', lang)}</div>
              <div className="metric-value">{stats.total_registered.toLocaleString() ?? 0}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">{t('phone.duplicates_blocked', lang)}</div>
              <div className="metric-value">{stats.duplicates_blocked.toLocaleString() ?? 0}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
