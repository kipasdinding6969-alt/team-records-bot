import { useEffect, useState } from 'react'
import { api, getAuthState, debug } from '../api'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'
import { PageHeader, Spinner, Empty } from '../components/SharedUI'

export default function MaintainerDash() {
  const { theme } = useTheme()
  const lang = getLang()
  const auth = getAuthState()

  const [activeTab, setActiveTab] = useState<'team' | 'reassign' | 'targets' | 'sla' | 'deposits'>('team')
  const [loading, setLoading] = useState(true)
  const [staff, setStaff] = useState<any[]>([])
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [reassignFrom, setReassignFrom] = useState('')
  const [reassignTo, setReassignTo] = useState('')


  const [depositGroupFilter, setDepositGroupFilter] = useState('')
  const [deposits, setDeposits] = useState<any[]>([])
  const [depositsLoading, setDepositsLoading] = useState(false)
  const [showDepositModal, setShowDepositModal] = useState(false)
  const [depositForm, setDepositForm] = useState({
    client_id: '',
    group_number: '',
    knife_number: '1',
    amount: '',
    pressure_amount: '',
    platform: 'MT5',
    role_type: 'frontdesk',
    note: '',
  })
  const [depositSubmitting, setDepositSubmitting] = useState(false)

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 3000)
  }

  const loadData = () => {
    setLoading(true)
    api.allStaff()
      .then(res => setStaff(res.filter(s => s.team === auth?.team_scope || auth?.role === 'owner')))
      .catch(debug)
      .finally(() => setLoading(false))
  }

  const loadDeposits = (group?: string) => {
    setDepositsLoading(true)
    api.maintainerDeposits(group || undefined, auth?.team_scope || undefined)
      .then(setDeposits)
      .catch(debug)
      .finally(() => setDepositsLoading(false))
  }

  useEffect(() => {
    loadData()
  }, [])

  useEffect(() => {
    if (activeTab === 'deposits') {
      loadDeposits(depositGroupFilter)
    }
  }, [activeTab])

  const handleUpdateStaff = async (id: number, updates: any) => {
    try {
      await api.updateStaff(id, updates)
      loadData()
    } catch(e) {
      showMessage('error', t('common.update_failed', lang))
    }
  }

  const handleReassign = async () => {
    if (!reassignFrom || !reassignTo) return
    try {
      await api.maintainerReassign(Number(reassignFrom), Number(reassignTo))
      showMessage('success', t('maintainer.bulk_reassign', lang) + ' OK')
      loadData()
      setReassignFrom('')
      setReassignTo('')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      showMessage('error', msg || 'Error')
    }
  }

  const handleDepositSubmit = async () => {
    if (!depositForm.client_id || !depositForm.group_number || !depositForm.amount) return
    setDepositSubmitting(true)
    try {
      await api.createMaintainerDeposit({
        client_id: Number(depositForm.client_id),
        group_number: depositForm.group_number,
        knife_number: Number(depositForm.knife_number),
        amount: parseFloat(depositForm.amount),
        pressure_amount: depositForm.pressure_amount ? parseFloat(depositForm.pressure_amount) : 0,
        platform: depositForm.platform,
        role_type: depositForm.role_type,
        note: depositForm.note || undefined,
      })
      setShowDepositModal(false)
      setDepositForm({ client_id: '', group_number: '', knife_number: '1', amount: '', pressure_amount: '', platform: 'MT5', role_type: 'frontdesk', note: '' })
      loadDeposits(depositGroupFilter)
      showMessage('success', t('maintainer.add_deposit', lang) + ' OK')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      showMessage('error', msg || 'Error')
    } finally {
      setDepositSubmitting(false)
    }
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowDepositModal(false)
    }
    if (showDepositModal) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [showDepositModal])

  if (loading) return <Spinner />

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: 'team', label: t('maintainer.my_team', lang) },
    { key: 'reassign', label: t('maintainer.reassign', lang) },
    { key: 'targets', label: t('maintainer.targets', lang) },
    { key: 'sla', label: t('maintainer.sla', lang) },
    { key: 'deposits', label: t('maintainer.deposits_tab', lang) },
  ]

  const depositTotals = deposits.reduce((acc, d) => ({
    amount: acc.amount + (d.amount || 0),
    pressure: acc.pressure + (d.pressure_amount || 0),
    total_in: acc.total_in + (d.total_in || d.amount || 0),
  }), { amount: 0, pressure: 0, total_in: 0 })

  return (
    <div className="page-container">
      <PageHeader title={t('maintainer.title', lang)} />

      {message && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      <div className="tab-bar">
        {tabs.map(tab => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="card">
        {activeTab === 'team' && (
          <div>
            <h3 className="section-title">{t('maintainer.team_members', lang)} ({staff.length})</h3>
            {staff.length === 0 ? <Empty /> : (
              <div className="overflow-x">
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('maintainer.name', lang)}</th>
                      <th>{t('maintainer.role', lang)}</th>
                      <th className="cell-center">{t('maintainer.status', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staff.map(s => (
                      <tr key={s.id}>
                        <td className="fw-600">{s.display_name}</td>
                        <td>
                           <select className="input w-auto" value={s.role} onChange={e => handleUpdateStaff(s.id, { role: e.target.value })}>
                             <option value="frontdesk">frontdesk</option>
                             <option value="maintenance">maintenance</option>
                             <option value="leader">leader</option>
                             <option value="customer_service">customer_service</option>
                             <option value="newbie">newbie</option>
                             <option value="viewer">viewer</option>
                           </select>
                        </td>
                        <td className="cell-center">
                           <button
                             className={`${s.is_active ? 'badge-success' : 'badge-danger'} pointer fs-12 fw-700 rounded-8 p-4-12`}
                             onClick={() => handleUpdateStaff(s.id, { is_active: !s.is_active })}
                           >
                             {s.is_active ? t('maintainer.active', lang) : t('maintainer.inactive', lang)}
                           </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reassign' && (
           <div>
             <h3 className="section-title">{t('maintainer.bulk_reassign', lang)}</h3>
             <div className="form-section max-w-500">
                <label>
                  <span className="field-label">{t('maintainer.source_staff', lang)}</span>
                  <select className="input" value={reassignFrom} onChange={e => setReassignFrom(e.target.value)}>
                    <option value="">{t('maintainer.select_source', lang)}</option>
                    {staff.map(s => <option key={s.id} value={s.id}>{s.display_name} ({s.client_count} clients)</option>)}
                  </select>
                </label>
                <div className="text-center fs-20 text-secondary">&#x25BC;</div>
                <label>
                  <span className="field-label">{t('maintainer.target_staff', lang)}</span>
                  <select className="input" value={reassignTo} onChange={e => setReassignTo(e.target.value)}>
                    <option value="">{t('maintainer.select_target', lang)}</option>
                    {staff.map(s => <option key={s.id} value={s.id}>{s.display_name}</option>)}
                  </select>
                </label>
                <button
                  className="btn-primary"
                  disabled={!reassignFrom || !reassignTo || reassignFrom === reassignTo}
                  onClick={handleReassign}
                >
                  {t('maintainer.bulk_reassign', lang)}
                </button>
             </div>
           </div>
        )}

        {activeTab === 'targets' && (
          <div>
            <h3 className="section-title">{t('maintainer.edit_target', lang)}</h3>
            <div className="flex-col gap-12">
              {staff.map(s => (
                 <div key={s.id} className="target-row">
                    <span className="fw-600 fs-14">{s.display_name}</span>
                    <div className="d-flex items-center gap-12">
                       <span className="field-label m-0">{t('maintainer.daily_target', lang)}</span>
                       <input
                         className="input text-center fw-700 w-80"
                         type="number"
                         defaultValue={s.daily_target}
                         onBlur={e => handleUpdateStaff(s.id, { daily_target: parseInt(e.target.value) || 0 })}
                       />
                    </div>
                 </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'sla' && (
          <div>
             <h3 className="section-title">{t('maintainer.sla', lang)}</h3>
             <div className="overflow-x">
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('maintainer.name', lang)}</th>
                      <th className="cell-right">{t('maintainer.active_clients', lang)}</th>
                      <th className="cell-right">{t('maintainer.sla_status', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staff.map(s => (
                      <tr key={s.id}>
                        <td className="fw-600">{s.display_name}</td>
                        <td className="cell-mono-right fw-600">{s.client_count}</td>
                        <td className="cell-right">
                           <span className={`${s.client_count > 20 ? 'badge-warning' : 'badge-success'} fs-12 fw-700`}>
                             {s.client_count > 20 ? t('maintainer.overloaded', lang) : t('maintainer.healthy', lang)}
                           </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
             </div>
          </div>
        )}

        {activeTab === 'deposits' && (
          <div>
            <div className="toolbar">
              <h3 className="section-title m-0">{t('maintainer.deposits_tab', lang)}</h3>
              <div className="toolbar-spacer" />
              <button className="btn-primary" onClick={() => setShowDepositModal(true)}>
                + {t('maintainer.add_deposit', lang)}
              </button>
            </div>

            <div className="toolbar">
              <label className="field-label m-0">{t('maintainer.group_number', lang)}:</label>
              <input className="input w-200" value={depositGroupFilter} onChange={e => setDepositGroupFilter(e.target.value)} placeholder={t('maintainer.group_number', lang)} />
              <button className="btn-primary" onClick={() => loadDeposits(depositGroupFilter)}>
                {t('common.search', lang)}
              </button>
            </div>

            {depositsLoading ? <Spinner /> : deposits.length === 0 ? <Empty label={t('common.no_data', lang)} /> : (
              <div className="overflow-x">
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('clients.phone', lang)}</th>
                      <th>{t('detail.platform', lang)}</th>
                      <th>{t('maintainer.cut', lang)} #</th>
                      <th className="cell-right">{t('detail.amount', lang)}</th>
                      <th className="cell-right">{t('maintainer.pressure', lang)}</th>
                      <th className="cell-right">{t('maintainer.total_in', lang)}</th>
                      <th>{t('clients.frontdesk', lang)}</th>
                      <th>{t('detail.date', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deposits.map((d: any, idx: number) => (
                      <tr key={d.id || idx}>
                        <td className="cell-mono fw-600">{d.phone || d.client_id}</td>
                        <td>{d.platform || '-'}</td>
                        <td>{d.knife_number || '-'}</td>
                        <td className="cell-mono-right text-success fw-600">${(d.amount || 0).toLocaleString()}</td>
                        <td className="cell-mono-right text-warning">${(d.pressure_amount || 0).toLocaleString()}</td>
                        <td className="cell-mono-right text-accent fw-700">${(d.total_in || d.amount || 0).toLocaleString()}</td>
                        <td>{d.frontdesk_name || d.role_type || '-'}</td>
                        <td className="fs-12 text-secondary">{d.created_at?.slice(0, 10) || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-top deposit-totals-row">
                      <td colSpan={3} className="fw-700 fs-14">{t('common.total', lang)}</td>
                      <td className="cell-mono-right text-success fw-700 fs-14">${depositTotals.amount.toLocaleString()}</td>
                      <td className="cell-mono-right text-warning fw-700 fs-14">${depositTotals.pressure.toLocaleString()}</td>
                      <td className="cell-mono-right text-accent fw-700 fs-14">${depositTotals.total_in.toLocaleString()}</td>
                      <td colSpan={2} />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add Deposit Modal */}
      {showDepositModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowDepositModal(false) }}>
          <div className="modal-content w-480">
            <h3 className="modal-title">{t('maintainer.add_deposit', lang)}</h3>

            <div className="form-grid">
              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('maintainer.client_id', lang)} *</span>
                  <input className="input" type="number" value={depositForm.client_id} onChange={e => setDepositForm(prev => ({ ...prev, client_id: e.target.value }))} required />
                </label>
                <label>
                  <span className="field-label">{t('maintainer.group_number', lang)} *</span>
                  <input className="input" value={depositForm.group_number} onChange={e => setDepositForm(prev => ({ ...prev, group_number: e.target.value }))} required />
                </label>
              </div>

              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('maintainer.cut', lang)} # (1-8) *</span>
                  <select className="input" value={depositForm.knife_number} onChange={e => setDepositForm(prev => ({ ...prev, knife_number: e.target.value }))}>
                    {[1,2,3,4,5,6,7,8].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label>
                  <span className="field-label">{t('detail.platform', lang)}</span>
                  <select className="input" value={depositForm.platform} onChange={e => setDepositForm(prev => ({ ...prev, platform: e.target.value }))}>
                    {['MT5', 'MT4', 'cTrader', 'Other'].map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
              </div>

              <div className="form-grid-2col">
                <label>
                  <span className="field-label">{t('detail.amount', lang)} *</span>
                  <input className="input" type="number" step="0.01" value={depositForm.amount} onChange={e => setDepositForm(prev => ({ ...prev, amount: e.target.value }))} required />
                </label>
                <label>
                  <span className="field-label">{t('maintainer.pressure', lang)}</span>
                  <input className="input" type="number" step="0.01" value={depositForm.pressure_amount} onChange={e => setDepositForm(prev => ({ ...prev, pressure_amount: e.target.value }))} />
                </label>
              </div>

              <label>
                <span className="field-label">{t('maintainer.role', lang)}</span>
                <select className="input" value={depositForm.role_type} onChange={e => setDepositForm(prev => ({ ...prev, role_type: e.target.value }))}>
                  <option value="frontdesk">{t('maintainer.role_frontdesk', lang)}</option>
                  <option value="opener">{t('maintainer.role_opener', lang)}</option>
                  <option value="newbie">{t('maintainer.role_newbie', lang)}</option>
                  <option value="hype">{t('maintainer.role_hype', lang)}</option>
                  <option value="cs">{t('maintainer.role_cs', lang)}</option>
                  <option value="maintenance">{t('maintainer.role_mt', lang)}</option>
                </select>
              </label>

              <label>
                <span className="field-label">{t('detail.link_note', lang)}</span>
                <textarea className="input textarea-resize min-h-60 h-auto" value={depositForm.note} onChange={e => setDepositForm(prev => ({ ...prev, note: e.target.value }))} />
              </label>

              <div className="modal-actions">
                <button className="btn-secondary flex-1" onClick={() => setShowDepositModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary flex-1"
                  onClick={handleDepositSubmit}
                  disabled={depositSubmitting || !depositForm.client_id || !depositForm.group_number || !depositForm.amount}
                >
                  {depositSubmitting ? '...' : t('common.confirm', lang)}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
