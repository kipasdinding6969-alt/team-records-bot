import { useState, useEffect } from 'react'
import { api, getAuthState } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'

const CATEGORIES = [
  { value: 'UK表单粉', key: 'category.uk_form' },
  { value: 'CA表单粉', key: 'category.ca_form' },
  { value: 'AU表单粉', key: 'category.au_form' },
  { value: 'EU表单粉', key: 'category.eu_form' },
  { value: '飞机筛选', key: 'category.tg_filter' },
  { value: 'RCS筛选', key: 'category.rcs_filter' },
]

const DAY_STATUSES = [
  { value: 'register', key: 'day_status.register' },
  { value: 'no_register', key: 'day_status.no_register' },
  { value: 'pending', key: 'day_status.pending' },
]

export default function FrontdeskEntry() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()

  const [phone, setPhone] = useState('')
  const [accountId, setAccountId] = useState('')
  const [nickname, setNickname] = useState('')
  const [source, setSource] = useState('telegram')
  const [platform, setPlatform] = useState('MT5')
  const [category, setCategory] = useState('')
  const [recruiter, setRecruiter] = useState(auth?.display_name || '')
  const [notes, setNotes] = useState('')
  const [clientCondition, setClientCondition] = useState('')
  const [day1Status, setDay1Status] = useState('pending')
  const [day2Status, setDay2Status] = useState('pending')

  const [phoneStatus, setPhoneStatus] = useState<any>(null)
  const [checkTimer, setCheckTimer] = useState<any>(null)
  const [submitting, setSubmitting] = useState(false)
  const [stats, setStats] = useState<any>(null)
  const [recent, setRecent] = useState<any[]>([])
  const [searchVal, setSearchVal] = useState('')
  const [formErrors, setFormErrors] = useState<Record<string, boolean>>({})

  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [searchMessage, setSearchMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [history, setHistory] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  const loadData = () => {
    api.phoneRegistryStats().then(setStats).catch(console.error)
    api.clients({ page: 1, per_page: 10 }).then(res => setRecent(res.clients)).catch(console.error)
  }

  const loadHistory = () => {
    setHistoryLoading(true)
    api.frontdeskHistory(auth?.staff_id || undefined)
      .then(res => setHistory(res.entries || []))
      .catch(console.error)
      .finally(() => setHistoryLoading(false))
  }

  useEffect(() => {
    loadData()
    loadHistory()
    return () => { if (checkTimer) clearTimeout(checkTimer) }
  }, [])

  function checkPhone(val: string) {
    if (checkTimer) clearTimeout(checkTimer)
    setPhoneStatus(null)
    if (val.replace(/[^\d]/g, '').length < 5) return
    const timer = setTimeout(() => {
      api.phoneCheck(val).then(res => {
        setPhoneStatus(res)
      }).catch(() => {})
    }, 400)
    setCheckTimer(timer)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const errors: Record<string, boolean> = {}
    if (!phone.trim()) errors.phone = true
    if (!category) errors.category = true
    setFormErrors(errors)
    if (Object.keys(errors).length > 0) {
      if (errors.category) showMessage('error', t('frontdesk.category', lang) + ' is required')
      return
    }
    setSubmitting(true)
    try {
      await api.createClient({
        phone: phone.trim(),
        source,
        account_id: accountId || undefined,
        nickname: nickname || undefined,
        platform: platform || undefined,
        phone_remark: notes || undefined,
        recruiter: recruiter || undefined,
        category: category || undefined,
        first_day_status: day1Status,
        second_day_status: day2Status,
        client_condition: clientCondition || undefined,
      })
      setPhone('')
      setAccountId('')
      setNickname('')
      setNotes('')
      setClientCondition('')
      setDay1Status('pending')
      setDay2Status('pending')
      setPhoneStatus(null)
      setCategory('')
      setFormErrors({})
      loadData()
      loadHistory()
      showMessage('success', t('frontdesk.submit', lang) + ' OK')
    } catch (err: any) {
      showMessage('error', err.message || 'Error')
    } finally {
      setSubmitting(false)
    }
  }

  const phoneStatusColor = phoneStatus?.status === 'taken' ? theme.danger : phoneStatus?.status === 'own' ? theme.warning : theme.success
  const phoneStatusIcon = phoneStatus?.status === 'taken' ? 'X' : phoneStatus?.status === 'own' ? '!' : phoneStatus?.status === 'available' ? '/' : null

  const getDayColor = (status: string) =>
    status === 'register' ? theme.success : status === 'no_register' ? theme.danger : undefined

  return (
    <div className="page-container">
      <PageHeader title={t('frontdesk.title', lang)} />

      {message && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`} style={{ marginBottom: 20 }}>
          {message.text}
        </div>
      )}

      <div className="frontdesk-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 3fr) minmax(280px, 2fr)', gap: 20, alignItems: 'start' }}>
        <style>{`@media (max-width: 768px) { .frontdesk-grid { grid-template-columns: 1fr !important; } }`}</style>
        {/* LEFT: Entry form */}
        <div className="card">
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Phone input - LARGE and prominent */}
            <div>
              <label className="field-label">
                {t('frontdesk.phone_input', lang)} *
              </label>
              <input
                className="input input-lg"
                required
                value={phone}
                onChange={e => { setPhone(e.target.value); checkPhone(e.target.value); setFormErrors(p => ({ ...p, phone: false })) }}
                style={{
                  border: formErrors.phone ? '2px solid ' + theme.danger : phoneStatus ? `2px solid ${phoneStatusColor}` : undefined,
                }}
                placeholder="+60123456789"
              />

              {/* Duplicate check banner */}
              {phoneStatus && (
                <div
                  style={{
                    marginTop: 8,
                    padding: '12px 20px',
                    borderRadius: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    background: phoneStatus.status === 'taken' ? theme.dangerBg : phoneStatus.status === 'own' ? theme.warningBg : theme.successBg,
                    color: phoneStatusColor,
                    border: `2px solid ${phoneStatusColor}40`,
                  }}
                >
                  <span style={{
                    width: 24, height: 24, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    background: phoneStatusColor, color: '#fff', fontSize: 12, fontWeight: 700, flexShrink: 0,
                  }}>
                    {phoneStatusIcon}
                  </span>
                  <span>
                    {phoneStatus.status === 'taken' && `${t('frontdesk.duplicate_other', lang).replace('{owner}', phoneStatus.owner).replace('{team}', phoneStatus.team || '').replace('{date}', phoneStatus.submitted_at?.slice(0, 10) || '')}`}
                    {phoneStatus.status === 'own' && `${t('frontdesk.duplicate_self', lang)}`}
                    {phoneStatus.status === 'available' && `${t('frontdesk.available', lang)}`}
                  </span>
                </div>
              )}
            </div>

            {/* Category selector - big clear buttons */}
            <div>
              <label className="field-label">
                {t('frontdesk.category', lang)} *
              </label>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 8,
                border: formErrors.category ? `2px solid ${theme.danger}` : undefined,
                borderRadius: 8,
                padding: formErrors.category ? 4 : 0,
              }}>
                {CATEGORIES.map(c => (
                  <button
                    key={c.value}
                    type="button"
                    className={category === c.value ? 'btn-primary' : 'btn-secondary'}
                    style={{ height: 44, fontSize: 14, fontWeight: 600, width: '100%' }}
                    onClick={() => { setCategory(c.value); setFormErrors(p => ({ ...p, category: false })) }}
                  >
                    {t(c.key, lang)}
                  </button>
                ))}
              </div>
            </div>

            {/* 2-column grid fields */}
            <div className="form-grid-2col">
              <div>
                <label className="field-label">
                  {t('clients.account_id', lang)}
                </label>
                <input className="input" value={accountId} onChange={e => setAccountId(e.target.value)} />
              </div>
              <div>
                <label className="field-label">
                  {t('clients.nickname', lang)}
                </label>
                <input className="input" value={nickname} onChange={e => setNickname(e.target.value)} />
              </div>
              <div>
                <label className="field-label">
                  {t('clients.source', lang)} *
                </label>
                <select className="input" value={source} onChange={e => setSource(e.target.value)} required>
                  {['telegram', 'facebook', 'instagram', 'tiktok', 'wechat', 'other'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label">
                  {t('clients.platform', lang)} *
                </label>
                <select className="input" value={platform} onChange={e => setPlatform(e.target.value)} required>
                  {['MT5', 'MT4', 'cTrader', 'Other'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label">
                  {t('clients.recruiter_label', lang)}
                </label>
                <input className="input" value={recruiter} onChange={e => setRecruiter(e.target.value)} />
              </div>
              <div>
                <label className="field-label">
                  {t('clients.notes', lang)}
                </label>
                <input className="input" value={notes} onChange={e => setNotes(e.target.value)} />
              </div>
            </div>

            {/* Day status toggles */}
            <div className="card" style={{ background: theme.bgElevated, padding: 20 }}>
              <label className="field-label" style={{ marginBottom: 12 }}>
                {t('frontdesk.day_status', lang)}
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {t('day_status.first_day', lang)}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {DAY_STATUSES.map(ds => {
                      const isActive = day1Status === ds.value
                      const color = getDayColor(ds.value)
                      return (
                        <button
                          key={ds.value}
                          type="button"
                          className={isActive ? 'btn-primary' : 'btn-secondary'}
                          style={{
                            flex: 1,
                            height: 36,
                            fontSize: 12,
                            fontWeight: 700,
                            padding: '0 8px',
                            background: isActive ? (color || undefined) : undefined,
                            borderColor: isActive && color ? color : undefined,
                          }}
                          onClick={() => setDay1Status(ds.value)}
                        >
                          {t(ds.key, lang)}
                        </button>
                      )
                    })}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: theme.textSecondary, marginBottom: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {t('day_status.second_day', lang)}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {DAY_STATUSES.map(ds => {
                      const isActive = day2Status === ds.value
                      const color = getDayColor(ds.value)
                      return (
                        <button
                          key={ds.value}
                          type="button"
                          className={isActive ? 'btn-primary' : 'btn-secondary'}
                          style={{
                            flex: 1,
                            height: 36,
                            fontSize: 12,
                            fontWeight: 700,
                            padding: '0 8px',
                            background: isActive ? (color || undefined) : undefined,
                            borderColor: isActive && color ? color : undefined,
                          }}
                          onClick={() => setDay2Status(ds.value)}
                        >
                          {t(ds.key, lang)}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Client condition */}
            <div>
              <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.3 }}>
                {t('frontdesk.client_condition', lang)}
              </label>
              <textarea
                className="input"
                value={clientCondition}
                onChange={e => setClientCondition(e.target.value)}
                style={{ resize: 'vertical', minHeight: 80, height: 'auto', padding: '12px 14px' }}
                placeholder={t('frontdesk.client_condition', lang) + '...'}
              />
            </div>

            {/* Submit button - full width, 48px */}
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting || phoneStatus?.status === 'taken'}
              style={{
                width: '100%',
                height: 48,
                fontSize: 16,
                fontWeight: 700,
                background: phoneStatus?.status === 'taken' ? theme.cardBorder : undefined,
                cursor: phoneStatus?.status === 'taken' ? 'not-allowed' : undefined,
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? '...' : t('frontdesk.submit', lang)}
            </button>
          </form>

          {/* Recent entries below form */}
          <h3 style={{ margin: '24px 0 12px', fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>
            {t('frontdesk.recent', lang)}
          </h3>
          {recent.length === 0 ? <Empty label={t('frontdesk.no_entries', lang)} /> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {recent.map(c => (
                <div key={c.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 20px', background: theme.bg, borderRadius: 8, border: `1px solid ${theme.cardBorder}`,
                }}>
                  <span style={{ fontWeight: 600, fontSize: 14, color: theme.textPrimary, fontFamily: 'monospace' }}>{c.phone}</span>
                  <span style={{ color: theme.textSecondary, fontSize: 12 }}>{c.source} | {c.created_at?.slice(11, 16)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RIGHT: Stats + Search */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Stats panel */}
          <div className="card">
            <h3 style={{ margin: '0 0 20px', fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>
              {t('frontdesk.stats', lang)}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              {[
                { label: t('phone.total_numbers', lang), value: stats?.total_registered || 0, color: theme.textPrimary },
                { label: t('phone.duplicates_blocked', lang), value: stats?.duplicates_blocked || 0, color: theme.danger },
                { label: t('frontdesk.today_count', lang), value: history.filter(h => h.created_at?.includes(new Date().toISOString().slice(0, 10))).length, color: theme.success },
              ].map((m, i) => (
                <div key={i} className="metric-card">
                  <div className="metric-value" style={{ color: m.color }}>{m.value}</div>
                  <div className="metric-label">{m.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Search panel */}
          <div className="card">
            <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>
              {t('common.search', lang)}
            </h3>
            <input
              className="input"
              placeholder={t('clients.search', lang)}
              value={searchVal}
              onChange={e => {
                setSearchVal(e.target.value)
                if (e.target.value.replace(/[^\d]/g, '').length >= 5) {
                  api.phoneCheck(e.target.value).then(res => {
                    if (res.found) {
                      setSearchMessage({ type: 'success', text: t('frontdesk.found_owner', lang).replace('{owner}', res.owner) })
                      setTimeout(() => setSearchMessage(null), 3000)
                    } else {
                      setSearchMessage({ type: 'error', text: t('common.no_data', lang) })
                      setTimeout(() => setSearchMessage(null), 3000)
                    }
                  }).catch(() => {})
                } else {
                  setSearchMessage(null)
                }
              }}
            />
            {searchMessage && (
              <div className={`alert ${searchMessage.type === 'error' ? 'alert-error' : 'alert-success'}`} style={{ marginTop: 8 }}>
                {searchMessage.text}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Entry History Table */}
      <div className="card" style={{ marginTop: 20 }}>
        <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700, color: theme.textPrimary }}>
          {t('frontdesk.history', lang)}
        </h3>
        {historyLoading ? <Spinner /> : history.length === 0 ? <Empty label={t('frontdesk.no_entries', lang)} /> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-grid-table">
              <thead>
                <tr>
                  <th>{t('clients.phone', lang)}</th>
                  <th>{t('frontdesk.category', lang)}</th>
                  <th>{t('day_status.first_day', lang)}</th>
                  <th>{t('day_status.second_day', lang)}</th>
                  <th>{t('frontdesk.client_condition', lang)}</th>
                  <th>{t('clients.status', lang)}</th>
                  <th>{t('detail.date', lang)}</th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry: any, idx: number) => (
                  <tr key={entry.id || idx}>
                    <td style={{ fontWeight: 600, fontFamily: 'monospace' }}>{entry.phone}</td>
                    <td>{entry.category || '-'}</td>
                    <td>
                      <span className={`pill-badge ${entry.day1_status === 'register' ? 'badge-success' : entry.day1_status === 'no_register' ? 'badge-danger' : 'badge-warning'}`}>
                        {entry.day1_status || t('day_status.pending', lang)}
                      </span>
                    </td>
                    <td>
                      <span className={`pill-badge ${entry.day2_status === 'register' ? 'badge-success' : entry.day2_status === 'no_register' ? 'badge-danger' : 'badge-warning'}`}>
                        {entry.day2_status || t('day_status.pending', lang)}
                      </span>
                    </td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {entry.condition || entry.phone_remark || '-'}
                    </td>
                    <td>
                      <span className={`pill-badge ${entry.status === 'registered' ? 'badge-success' : 'badge-warning'}`}>
                        {entry.status || 'new'}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: theme.textSecondary }}>{entry.created_at?.slice(0, 10) || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
