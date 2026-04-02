import { useState, useEffect } from 'react'
import { api, getAuthState, debug } from '../api'
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
    setTimeout(() => setMessage(null), 3000)
  }

  const loadData = () => {
    api.phoneRegistryStats().then(setStats).catch(debug)
    api.clients({ page: 1, per_page: 10 }).then(res => setRecent(res.clients)).catch(debug)
  }

  const loadHistory = () => {
    setHistoryLoading(true)
    api.frontdeskHistory(auth?.staff_id || undefined)
      .then(res => setHistory(res.entries || []))
      .catch(debug)
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

  const getDayColor = (status: string) =>
    status === 'register' ? theme.success : status === 'no_register' ? theme.danger : undefined

  return (
    <div className="page-container">
      <PageHeader title={t('frontdesk.title', lang)} />

      {message && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'} mb-20`}>
          {message.text}
        </div>
      )}

      <div className="frontdesk-layout">
        {/* LEFT: Entry form */}
        <div className="card">
          <form onSubmit={handleSubmit} className="flex-col gap-20">
            {/* Phone input - LARGE and prominent */}
            <div>
              <label className="field-label">
                {t('frontdesk.phone_input', lang)} *
              </label>
              <input
                className={`input input-lg${formErrors.phone ? ' border-danger' : ''}`}
                required
                value={phone}
                onChange={e => { setPhone(e.target.value); checkPhone(e.target.value); setFormErrors(p => ({ ...p, phone: false })) }}
                style={phoneStatus && !formErrors.phone ? { border: `2px solid ${phoneStatusColor}` } : undefined}
                placeholder="+60123456789"
              />

              {/* Duplicate check banner */}
              {phoneStatus && (
                <div
                  className={`phone-status-banner mt-8 ${phoneStatus.status === 'taken' ? 'badge-danger' : phoneStatus.status === 'own' ? 'badge-warning' : 'badge-success'}`}
                >
                  <span className={`phone-status-icon ${phoneStatus.status === 'taken' ? 'dot-danger' : phoneStatus.status === 'own' ? 'dot-warning' : 'dot-success'}`}>
                    {phoneStatus?.status === 'taken' ? 'X' : phoneStatus?.status === 'own' ? '!' : phoneStatus?.status === 'available' ? '/' : null}
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
              <div
                className={`category-grid${formErrors.category ? ' category-grid-error' : ''}`}
              >
                {CATEGORIES.map(c => (
                  <button
                    key={c.value}
                    type="button"
                    className={`category-btn ${category === c.value ? 'btn-primary' : 'btn-secondary'}`}
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
            <div className="card bg-elevated p-20">
              <label className="field-label mb-12">
                {t('frontdesk.day_status', lang)}
              </label>
              <div className="day-status-grid">
                <div>
                  <div className="field-label mb-8">
                    {t('day_status.first_day', lang)}
                  </div>
                  <div className="day-status-buttons">
                    {DAY_STATUSES.map(ds => {
                      const isActive = day1Status === ds.value
                      const color = getDayColor(ds.value)
                      return (
                        <button
                          key={ds.value}
                          type="button"
                          className={`day-status-btn ${isActive ? 'btn-primary' : 'btn-secondary'}`}
                          style={{
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
                  <div className="field-label mb-8">
                    {t('day_status.second_day', lang)}
                  </div>
                  <div className="day-status-buttons">
                    {DAY_STATUSES.map(ds => {
                      const isActive = day2Status === ds.value
                      const color = getDayColor(ds.value)
                      return (
                        <button
                          key={ds.value}
                          type="button"
                          className={`day-status-btn ${isActive ? 'btn-primary' : 'btn-secondary'}`}
                          style={{
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
              <label className="field-label">
                {t('frontdesk.client_condition', lang)}
              </label>
              <textarea
                className="input textarea-resize min-h-80"
                value={clientCondition}
                onChange={e => setClientCondition(e.target.value)}
                placeholder={t('frontdesk.client_condition', lang) + '...'}
              />
            </div>

            {/* Submit button - full width */}
            <button
              type="submit"
              className={`btn-primary btn-lg w-full fw-700 fs-16${phoneStatus?.status === 'taken' ? ' btn-blocked' : ''}${submitting ? ' opacity-70' : ''}`}
              disabled={submitting || phoneStatus?.status === 'taken'}
            >
              {submitting ? '...' : t('frontdesk.submit', lang)}
            </button>
          </form>

          {/* Recent entries below form */}
          <h3 className="heading-sm mt-20 mb-12">
            {t('frontdesk.recent', lang)}
          </h3>
          {recent.length === 0 ? <Empty label={t('frontdesk.no_entries', lang)} /> : (
            <div className="flex-col gap-8">
              {recent.map(c => (
                <div key={c.id} className="recent-entry">
                  <span className="fw-600 fs-14 text-primary cell-mono">{c.phone}</span>
                  <span className="text-secondary fs-12">{c.source} | {c.created_at?.slice(11, 16)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* RIGHT: Stats + Search */}
        <div className="flex-col gap-20">
          {/* Stats panel */}
          <div className="card">
            <h3 className="heading-sm mb-20">
              {t('frontdesk.stats', lang)}
            </h3>
            <div className="form-grid-3col">
              {[
                { label: t('phone.total_numbers', lang), value: stats?.total_registered || 0, cls: 'text-primary' },
                { label: t('phone.duplicates_blocked', lang), value: stats?.duplicates_blocked || 0, cls: 'text-danger' },
                { label: t('frontdesk.today_count', lang), value: history.filter(h => h.created_at?.includes(new Date().toISOString().slice(0, 10))).length, cls: 'text-success' },
              ].map((m) => (
                <div key={m.label} className="metric-card">
                  <div className={`metric-value ${m.cls}`}>{m.value}</div>
                  <div className="metric-label">{m.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Search panel */}
          <div className="card">
            <h3 className="heading-sm mb-12">
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
                    if (res.status === 'taken' || res.status === 'own') {
                      setSearchMessage({ type: 'success', text: t('frontdesk.found_owner', lang).replace('{owner}', res.owner || '') })
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
              <div className={`alert ${searchMessage.type === 'error' ? 'alert-error' : 'alert-success'} mt-8`}>
                {searchMessage.text}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Entry History Table */}
      <div className="card mt-20">
        <h3 className="heading-lg mb-20">
          {t('frontdesk.history', lang)}
        </h3>
        {historyLoading ? <Spinner /> : history.length === 0 ? <Empty label={t('frontdesk.no_entries', lang)} /> : (
          <div className="overflow-x">
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
                    <td className="fw-600 cell-mono">{entry.phone}</td>
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
                    <td className="truncate max-w-200">
                      {entry.condition || entry.phone_remark || '-'}
                    </td>
                    <td>
                      <span className={`pill-badge ${entry.status === 'registered' ? 'badge-success' : 'badge-warning'}`}>
                        {entry.status || 'new'}
                      </span>
                    </td>
                    <td className="fs-12 text-secondary">{entry.created_at?.slice(0, 10) || '-'}</td>
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
