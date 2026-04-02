import { useState, useEffect } from 'react'
import { api } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'
import type { GroupInteraction } from '../types'

interface FormData {
  client_id: string
  group_id: string
  actor_role: string
  day_number: string
  script_completed: boolean
  client_left_group: boolean
  client_pm_character: boolean
  notes: string
}

const INITIAL_FORM: FormData = {
  client_id: '',
  group_id: '',
  actor_role: 'newbie_actor',
  day_number: '1',
  script_completed: false,
  client_left_group: false,
  client_pm_character: false,
  notes: '',
}

function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}

function thirtyDaysAgo(): string {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().split('T')[0]
}

export default function GroupInteractions() {
  const { theme } = useTheme()
  const lang = getLang()

  const [fromDate, setFromDate] = useState(thirtyDaysAgo())
  const [toDate, setToDate] = useState(todayStr())
  const [rows, setRows] = useState<GroupInteraction[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState<FormData>({ ...INITIAL_FORM })
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const perPage = 50

  const showMsg = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 3000)
  }

  const loadData = (p = 1) => {
    setLoading(true)
    api.listGroupInteractions({ from_date: fromDate, to_date: toDate, page: p, per_page: perPage })
      .then(res => {
        setRows(res.items)
        setTotal(res.total)
        setPage(res.page)
      })
      .catch(err => showMsg('error', err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData(1)
  }, [fromDate, toDate])

  const handleSubmit = async () => {
    const clientId = parseInt(form.client_id, 10)
    if (!clientId || isNaN(clientId)) {
      showMsg('error', 'Client ID is required')
      return
    }
    setSubmitting(true)
    try {
      await api.addGroupInteraction(clientId, {
        group_id: form.group_id || undefined,
        actor_role: form.actor_role,
        day_number: form.day_number ? parseInt(form.day_number, 10) : undefined,
        script_completed: form.script_completed,
        client_left_group: form.client_left_group,
        client_pm_character: form.client_pm_character,
        notes: form.notes || undefined,
      })
      showMsg('success', 'Entry created')
      setShowModal(false)
      setForm({ ...INITIAL_FORM })
      loadData(1)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      showMsg('error', msg)
    } finally {
      setSubmitting(false)
    }
  }

  // Stats computation
  const totalClients = rows.length
  const day1Completed = rows.filter(r => r.first_day_status === 'register' || r.script_completed).length
  const day1Rate = totalClients > 0 ? Math.round((day1Completed / totalClients) * 100) : 0
  const leftCount = rows.filter(r => r.client_left_group).length
  const leftRate = totalClients > 0 ? Math.round((leftCount / totalClients) * 100) : 0

  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="page-container">
      <PageHeader title={t('gi.title', lang)} sub={t('gi.subtitle', lang)} />

      {/* Message banner */}
      {message && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      {/* Summary stats */}
      <div className="grid-3 mb-20">
        <div className="glass-card stat-card">
          <div className="stat-label">{t('gi.total_clients', lang)}</div>
          <div className="stat-value">{total}</div>
        </div>
        <div className="glass-card stat-card">
          <div className="stat-label">{t('gi.script_completion', lang)}</div>
          <div className="stat-value">{day1Rate}%</div>
        </div>
        <div className="glass-card stat-card">
          <div className="stat-label">{t('gi.left_rate', lang)}</div>
          <div className="stat-value" style={{ color: theme.danger }}>{leftRate}%</div>
        </div>
      </div>

      {/* Controls: date pickers + new entry button */}
      <div className="toolbar">
        <label className="field-label mb-0">{t('gi.date_from', lang)}</label>
        <input
          type="date"
          className="input w-auto"
          value={fromDate}
          onChange={e => setFromDate(e.target.value)}
        />
        <label className="field-label mb-0">{t('gi.date_to', lang)}</label>
        <input
          type="date"
          className="input w-auto"
          value={toDate}
          onChange={e => setToDate(e.target.value)}
        />
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + {t('gi.new_entry', lang)}
        </button>
      </div>

      {/* Data table */}
      {loading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty label={t('gi.no_data', lang)} />
      ) : (
        <div className="overflow-x">
          <table className="data-grid-table">
            <thead>
              <tr>
                <th>{t('gi.join_date', lang)}</th>
                <th>{t('gi.group_num', lang)}</th>
                <th>{t('gi.client_phone', lang)}</th>
                <th>{t('gi.client_id', lang)}</th>
                <th>{t('gi.frontdesk_maintainer', lang)}</th>
                <th>{t('gi.platform', lang)}</th>
                <th>{t('gi.day1_script', lang)}</th>
                <th>{t('gi.day2_script', lang)}</th>
                <th>{t('gi.client_left', lang)}</th>
                <th>{t('gi.newbie_followup', lang)}</th>
                <th>{t('gi.passerby', lang)}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id}>
                  <td>{row.created_at ? row.created_at.split('T')[0] : '-'}</td>
                  <td>{row.group_id || '-'}</td>
                  <td>{row.client_phone || '-'}</td>
                  <td>{row.client_account_id || String(row.client_id)}</td>
                  <td>{row.frontdesk_name || '-'}</td>
                  <td>{row.client_platform || '-'}</td>
                  <td>
                    <span className={`pill-badge ${row.first_day_status === 'register' ? 'badge-success' : 'badge-warning'}`}>
                      {row.first_day_status === 'register' ? t('gi.completed', lang) : t('gi.pending', lang)}
                    </span>
                  </td>
                  <td>
                    <span className={`pill-badge ${row.second_day_status === 'register' ? 'badge-success' : 'badge-warning'}`}>
                      {row.second_day_status === 'register' ? t('gi.completed', lang) : t('gi.pending', lang)}
                    </span>
                  </td>
                  <td>
                    <span className={`pill-badge ${row.client_left_group ? 'badge-danger' : 'badge-muted'}`}>
                      {row.client_left_group ? t('gi.yes', lang) : t('gi.no', lang)}
                    </span>
                  </td>
                  <td>
                    {row.actor_role === 'newbie_actor'
                      ? (row.actor_name || t('gi.newbie_actor', lang))
                      : t('gi.not_joined', lang)}
                  </td>
                  <td>
                    <span className={`pill-badge ${row.actor_role === 'passerby' ? 'badge-success' : 'badge-muted'}`}>
                      {row.actor_role === 'passerby' ? t('gi.yes', lang) : t('gi.no', lang)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="btn-secondary btn-sm"
            disabled={page <= 1}
            onClick={() => loadData(page - 1)}
          >
            &laquo;
          </button>
          <span className="pagination-info">{page} / {totalPages}</span>
          <button
            className="btn-secondary btn-sm"
            disabled={page >= totalPages}
            onClick={() => loadData(page + 1)}
          >
            &raquo;
          </button>
        </div>
      )}

      {/* New Entry Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content glass-card" onClick={e => e.stopPropagation()}>
            <h3 className="section-title">{t('gi.new_entry', lang)}</h3>

            <div className="form-grid">
              <div className="form-section">
                <label className="field-label">{t('gi.client_id', lang)} *</label>
                <input
                  type="number"
                  className="input"
                  value={form.client_id}
                  onChange={e => setForm({ ...form, client_id: e.target.value })}
                  placeholder="Client ID"
                />
              </div>

              <div className="form-section">
                <label className="field-label">{t('gi.group_num', lang)}</label>
                <input
                  type="text"
                  className="input"
                  value={form.group_id}
                  onChange={e => setForm({ ...form, group_id: e.target.value })}
                  placeholder="Group ID"
                />
              </div>

              <div className="form-section">
                <label className="field-label">{t('gi.actor_role', lang)}</label>
                <select
                  className="input"
                  value={form.actor_role}
                  onChange={e => setForm({ ...form, actor_role: e.target.value })}
                >
                  <option value="newbie_actor">{t('gi.newbie_actor', lang)}</option>
                  <option value="group_hype">{t('gi.group_hype', lang)}</option>
                  <option value="passerby">{t('gi.passerby', lang)}</option>
                </select>
              </div>

              <div className="form-section">
                <label className="field-label">{t('gi.day_number', lang)}</label>
                <input
                  type="number"
                  className="input"
                  value={form.day_number}
                  onChange={e => setForm({ ...form, day_number: e.target.value })}
                  min="1"
                  max="30"
                />
              </div>

              <div className="form-section">
                <label className="field-label">
                  <input
                    type="checkbox"
                    checked={form.script_completed}
                    onChange={e => setForm({ ...form, script_completed: e.target.checked })}
                  />
                  {' '}{t('gi.completed', lang)} ({t('gi.day1_script', lang)})
                </label>
              </div>

              <div className="form-section">
                <label className="field-label">
                  <input
                    type="checkbox"
                    checked={form.client_left_group}
                    onChange={e => setForm({ ...form, client_left_group: e.target.checked })}
                  />
                  {' '}{t('gi.client_left', lang)}
                </label>
              </div>

              <div className="form-section" style={{ gridColumn: '1 / -1' }}>
                <label className="field-label">{t('gi.notes', lang)}</label>
                <textarea
                  className="input"
                  rows={3}
                  value={form.notes}
                  onChange={e => setForm({ ...form, notes: e.target.value })}
                />
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                {t('gi.cancel', lang)}
              </button>
              <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? t('common.loading', lang) : t('gi.save', lang)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
