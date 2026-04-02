import { useEffect, useState } from 'react'
import { api, getAuthState } from '../api'
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
  const [reassignLoading, setReassignLoading] = useState(false)

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
    setTimeout(() => setMessage(null), 4000)
  }

  const loadData = () => {
    setLoading(true)
    api.allStaff()
      .then(res => setStaff(res.filter(s => s.team === auth?.team_scope || auth?.role === 'owner')))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  const loadDeposits = (group?: string) => {
    setDepositsLoading(true)
    api.maintainerDeposits(group || undefined, auth?.team_scope || undefined)
      .then(setDeposits)
      .catch(console.error)
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

  const handleBulkReassign = async () => {
    if (!reassignFrom || !reassignTo || reassignFrom === reassignTo) return
    showMessage('error', 'Bulk reassign is coming soon. This feature is not yet implemented.')
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
    } catch (err: any) {
      showMessage('error', err.message || 'Error')
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
              <div style={{ overflowX: 'auto' }}>
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('maintainer.name', lang)}</th>
                      <th>{t('maintainer.role', lang)}</th>
                      <th style={{ textAlign: 'center' }}>{t('maintainer.status', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staff.map(s => (
                      <tr key={s.id}>
                        <td style={{ fontWeight: 600 }}>{s.display_name}</td>
                        <td>
                           <select className="input" value={s.role} onChange={e => handleUpdateStaff(s.id, { role: e.target.value })} style={{ width: 'auto' }}>
                             <option value="frontdesk">frontdesk</option>
                             <option value="newbie">newbie</option>
                             <option value="customer_service">customer_service</option>
                           </select>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                           <button
                             className={s.is_active ? 'badge-success' : 'badge-danger'}
                             style={{ cursor: 'pointer', fontSize: 12, fontWeight: 700, padding: '4px 12px', borderRadius: 8 }}
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
             <div className="form-grid" style={{ maxWidth: 500, background: theme.bgElevated, padding: 20, borderRadius: 12, border: `1px solid ${theme.cardBorder}` }}>
                <label>
                  <span className="field-label">{t('maintainer.source_staff', lang)}</span>
                  <select className="input" value={reassignFrom} onChange={e => setReassignFrom(e.target.value)}>
                    <option value="">{t('maintainer.select_source', lang)}</option>
                    {staff.map(s => <option key={s.id} value={s.id}>{s.display_name} ({s.client_count} clients)</option>)}
                  </select>
                </label>
                <div style={{ textAlign: 'center', fontSize: 20, color: theme.textSecondary }}>&#8595;</div>
                <label>
                  <span className="field-label">{t('maintainer.target_staff', lang)}</span>
                  <select className="input" value={reassignTo} onChange={e => setReassignTo(e.target.value)}>
                    <option value="">{t('maintainer.select_target', lang)}</option>
                    {staff.map(s => <option key={s.id} value={s.id}>{s.display_name}</option>)}
                  </select>
                </label>
                <button
                  className="btn-primary"
                  onClick={handleBulkReassign}
                  disabled={reassignLoading || !reassignFrom || !reassignTo || reassignFrom === reassignTo}
                >
                  {reassignLoading ? '...' : t('maintainer.bulk_reassign', lang)}
                </button>
             </div>
           </div>
        )}

        {activeTab === 'targets' && (
          <div>
            <h3 className="section-title">{t('maintainer.edit_target', lang)}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {staff.map(s => (
                 <div key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: theme.bgElevated, borderRadius: 8, border: `1px solid ${theme.cardBorder}` }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{s.display_name}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                       <span className="field-label" style={{ marginBottom: 0 }}>{t('maintainer.daily_target', lang)}</span>
                       <input
                         className="input"
                         type="number"
                         value={s.daily_target}
                         onChange={e => handleUpdateStaff(s.id, { daily_target: parseInt(e.target.value) || 0 })}
                         style={{ width: 80, textAlign: 'center', fontWeight: 700 }}
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
             <div style={{ overflowX: 'auto' }}>
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('maintainer.name', lang)}</th>
                      <th style={{ textAlign: 'right' }}>{t('maintainer.active_clients', lang)}</th>
                      <th style={{ textAlign: 'right' }}>{t('maintainer.sla_status', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staff.map(s => (
                      <tr key={s.id}>
                        <td style={{ fontWeight: 600 }}>{s.display_name}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{s.client_count}</td>
                        <td style={{ textAlign: 'right' }}>
                           <span className={s.client_count > 20 ? 'badge-warning' : 'badge-success'} style={{ fontSize: 12, fontWeight: 700 }}>
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
              <h3 className="section-title" style={{ margin: 0 }}>{t('maintainer.deposits_tab', lang)}</h3>
              <div className="toolbar-spacer" />
              <button className="btn-primary" onClick={() => setShowDepositModal(true)}>
                + {t('maintainer.add_deposit', lang)}
              </button>
            </div>

            <div className="toolbar">
              <label className="field-label" style={{ marginBottom: 0 }}>{t('maintainer.group_number', lang)}:</label>
              <input className="input" value={depositGroupFilter} onChange={e => setDepositGroupFilter(e.target.value)} placeholder={t('maintainer.group_number', lang)} style={{ width: 200 }} />
              <button className="btn-primary" onClick={() => loadDeposits(depositGroupFilter)}>
                {t('common.search', lang)}
              </button>
            </div>

            {depositsLoading ? <Spinner /> : deposits.length === 0 ? <Empty label={t('common.no_data', lang)} /> : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      <th>{t('clients.phone', lang)}</th>
                      <th>{t('detail.platform', lang)}</th>
                      <th>{t('maintainer.cut', lang)} #</th>
                      <th style={{ textAlign: 'right' }}>{t('detail.amount', lang)}</th>
                      <th style={{ textAlign: 'right' }}>{t('maintainer.pressure', lang)}</th>
                      <th style={{ textAlign: 'right' }}>{t('maintainer.total_in', lang)}</th>
                      <th>{t('clients.frontdesk', lang)}</th>
                      <th>{t('detail.date', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deposits.map((d: any, idx: number) => (
                      <tr key={d.id || idx}>
                        <td style={{ fontWeight: 600, fontFamily: 'monospace' }}>{d.phone || d.client_id}</td>
                        <td>{d.platform || '-'}</td>
                        <td>{d.knife_number || '-'}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600, fontFamily: 'monospace', color: theme.success }}>${(d.amount || 0).toLocaleString()}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace', color: theme.warning }}>${(d.pressure_amount || 0).toLocaleString()}</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: theme.accent }}>${(d.total_in || d.amount || 0).toLocaleString()}</td>
                        <td>{d.frontdesk_name || d.role_type || '-'}</td>
                        <td style={{ fontSize: 12, color: theme.textSecondary }}>{d.created_at?.slice(0, 10) || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ borderTop: `2px solid ${theme.cardBorder}`, background: `${theme.accent}08` }}>
                      <td colSpan={3} style={{ fontWeight: 700, fontSize: 14 }}>{t('common.total', lang)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, fontSize: 14, fontFamily: 'monospace', color: theme.success }}>${depositTotals.amount.toLocaleString()}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, fontSize: 14, fontFamily: 'monospace', color: theme.warning }}>${depositTotals.pressure.toLocaleString()}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, fontSize: 14, fontFamily: 'monospace', color: theme.accent }}>${depositTotals.total_in.toLocaleString()}</td>
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
          <div className="modal-content" style={{ width: 480 }}>
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
                <textarea className="input" value={depositForm.note} onChange={e => setDepositForm(prev => ({ ...prev, note: e.target.value }))} style={{ resize: 'vertical', minHeight: 60, height: 'auto' }} />
              </label>

              <div className="modal-actions">
                <button className="btn-secondary" style={{ flex: 1 }} onClick={() => setShowDepositModal(false)}>
                  {t('common.cancel', lang)}
                </button>
                <button
                  className="btn-primary"
                  style={{ flex: 1 }}
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
