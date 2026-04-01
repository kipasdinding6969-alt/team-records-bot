import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { Client, ClientList } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from './Dashboard'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

const STATUSES = ['', 'new', 'contacted', 'replied', 'registered', 'training', 'ordered', 'withdrew', 'ghosted', 'dead']
const PER_PAGE = 50

export default function Clients() {
  const { theme } = useTheme()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<ClientList | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()
  const [showAdd, setShowAdd] = useState(false)
  const [addPhone, setAddPhone] = useState('')
  const [addSource, setAddSource] = useState('web')
  const [addNickname, setAddNickname] = useState('')
  const [addAccountId, setAddAccountId] = useState('')
  const [addCategory, setAddCategory] = useState('')
  const [addRecruiter, setAddRecruiter] = useState('')
  const [addPlatform, setAddPlatform] = useState('')
  const [addError, setAddError] = useState('')
  const [addSuccess, setAddSuccess] = useState('')
  const [phoneStatus, setPhoneStatus] = useState<any>(null)
  const [checkTimer, setCheckTimer] = useState<any>(null)
  const [addSubmitting, setAddSubmitting] = useState(false)

  const status = params.get('status') || ''
  const search = params.get('search') || ''
  const page = parseInt(params.get('page') || '1', 10)

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  useEffect(() => {
    setLoading(true)
    api.clients({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [status, search, page])

  const totalPages = data ? Math.ceil(data.total / PER_PAGE) : 1

  function checkPhone(phone: string) {
    if (checkTimer) clearTimeout(checkTimer)
    setPhoneStatus(null)
    setAddError('')
    if (phone.replace(/[^\d]/g, '').length < 5) return
    const timer = setTimeout(() => {
      api.phoneCheck(phone).then(setPhoneStatus).catch(() => {})
    }, 400)
    setCheckTimer(timer)
  }

  async function submitNewClient() {
    if (!addPhone.trim() || !addSource) return
    setAddSubmitting(true)
    setAddError('')
    setAddSuccess('')
    try {
      const res = await api.createClient({
        phone: addPhone.trim(), source: addSource,
        nickname: addNickname || undefined, account_id: addAccountId || undefined,
        category: addCategory || undefined, recruiter: addRecruiter || undefined,
        platform: addPlatform || undefined,
      })
      setAddSuccess(`Client #${res.client_id} created`)
      setAddPhone('')
      setAddNickname('')
      setPhoneStatus(null)
      // Refresh list
      setLoading(true)
      api.clients({ status: status || undefined, search: search || undefined, page, per_page: PER_PAGE })
        .then(setData).finally(() => setLoading(false))
    } catch (e: any) {
      const msg = typeof e.message === 'string' ? e.message : 'Failed to create client'
      setAddError(msg)
    } finally {
      setAddSubmitting(false)
    }
  }

  return (
    <div>
      <PageHeader title="客户列表 (Clients)" sub="Manage and view all your clients." />

      {/* Filters */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search phone or source..."
          value={search}
          onChange={e => setParam('search', e.target.value)}
          style={getInputStyle(theme)}
        />
        <select
          value={status}
          onChange={e => setParam('status', e.target.value)}
          style={{ ...getInputStyle(theme), width: 180 }}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s ? STATUS_LABELS[s] || s : 'All Statuses'}
            </option>
          ))}
        </select>
        <button className="glass-btn"
          onClick={() => api.exportClients(status || undefined, undefined).catch(console.error)}
          style={getBtnStyle(theme)}
        >
          📥 Export CSV
        </button>
        <button
          onClick={() => { setShowAdd(true); setAddError(''); setAddSuccess(''); setPhoneStatus(null) }}
          style={{ ...getBtnStyle(theme), background: '#22c55e', color: '#fff', border: 'none', fontWeight: 600 }}
        >
          ➕ 新增客户
        </button>
        {data && (
          <span style={{ fontSize: 14, fontWeight: 600, color: theme.textSecondary, marginLeft: 'auto' }}>
            Total: {data.total.toLocaleString()} records
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <Spinner />
      ) : (
        <div style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 12, boxShadow: theme.shadow, overflow: 'hidden' }}>
          {!data || data.clients.length === 0 ? (
            <Empty />
          ) : (
            <>
              <div style={{ overflowX: 'auto', maxHeight: 'calc(100vh - 280px)' }}>
                <style>{`
                  .data-grid-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                  }
                  .data-grid-table th {
                    padding: 10px 12px;
                    text-align: left;
                    color: ${theme.textSecondary};
                    font-weight: 700;
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    white-space: nowrap;
                    border-bottom: 1px solid ${theme.cardBorder};
                    border-right: 1px solid ${theme.cardBorder};
                    background: ${theme.bg}E6;
                    backdrop-filter: blur(12px);
                    position: sticky;
                    top: 0;
                    z-index: 1;
                    box-shadow: 0 1px 2px ${theme.cardBorder};
                  }
                  .data-grid-table th:last-child {
                    border-right: none;
                  }
                  .data-grid-table td {
                    padding: 8px 12px;
                    border-bottom: 1px solid ${theme.cardBorder};
                    border-right: 1px solid ${theme.cardBorder};
                    color: ${theme.textPrimary};
                    transition: background 0.15s ease;
                  }
                  .data-grid-table td:last-child {
                    border-right: none;
                  }
                  .data-grid-row {
                    background: ${theme.cardBg};
                    cursor: pointer;
                    transition: all 0.15s ease;
                  }
                  .data-grid-row:hover {
                    background: ${theme.accentLight};
                  }
                  .data-grid-row:hover td {
                    background: ${theme.accentLight};
                  }
                  .data-grid-row td:hover {
                    background: ${theme.accent}20; /* Cell specific highlight */
                  }
                `}</style>
                <table className="data-grid-table">
                  <thead>
                    <tr>
                      {['Phone', 'Status', 'Source', 'Owner', 'Team', 'Deposit', 'Next Followup', 'Created At'].map(h => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.clients.map((c: Client, i: number) => (
                      <tr className="data-grid-row"
                        key={c.id}
                        onClick={() => nav(`/clients/${c.id}`)}
                      >
                        <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                          {c.phone}
                        </td>
                        <td>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: 6,
                              fontSize: 11,
                              background: `${STATUS_COLORS[c.status] || theme.textSecondary}15`,
                              color: STATUS_COLORS[c.status] || theme.textSecondary,
                              fontWeight: 700,
                              whiteSpace: 'nowrap',
                              display: 'inline-block',
                              border: `1px solid ${STATUS_COLORS[c.status] || theme.textSecondary}30`
                            }}
                          >
                            {STATUS_LABELS[c.status] || c.status}
                          </span>
                        </td>
                        <td style={{ color: theme.textSecondary, fontWeight: 500 }}>{c.source || '—'}</td>
                        <td style={{ fontWeight: 500 }}>{c.frontdesk_name || '—'}</td>
                        <td style={{ color: theme.textSecondary, fontWeight: 500 }}>{c.team || '—'}</td>
                        <td style={{ fontFamily: 'monospace', color: c.total_deposited > 0 ? theme.success : theme.textSecondary, fontWeight: c.total_deposited > 0 ? 700 : 500 }}>
                          {c.total_deposited > 0 ? `$${c.total_deposited.toLocaleString()}` : '—'}
                        </td>
                        <td style={{ fontFamily: 'monospace', color: c.next_followup ? theme.warning : theme.textSecondary, fontSize: 12, fontWeight: 500 }}>
                          {c.next_followup ? new Date(c.next_followup).toLocaleDateString() : '—'}
                        </td>
                        <td style={{ fontFamily: 'monospace', color: theme.textSecondary, fontSize: 12, fontWeight: 500 }}>
                          {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div
                  style={{
                    display: 'flex',
                    gap: 12,
                    padding: '16px 24px',
                    borderTop: `1px solid ${theme.cardBorder}`,
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    background: theme.bg,
                  }}
                >
                  <button className="glass-btn"
                    onClick={() => setParam('page', String(page - 1))}
                    disabled={page <= 1}
                    style={{ ...getBtnStyle(theme), opacity: page <= 1 ? 0.4 : 1 }}
                  >
                    Previous
                  </button>
                  <span style={{ fontSize: 14, fontWeight: 600, color: theme.textSecondary }}>
                    Page {page} of {totalPages}
                  </span>
                  <button className="glass-btn"
                    onClick={() => setParam('page', String(page + 1))}
                    disabled={page >= totalPages}
                    style={{ ...getBtnStyle(theme), opacity: page >= totalPages ? 0.4 : 1 }}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Add Client Modal */}
      {showAdd && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          animation: 'modalFadeIn 0.2s ease-out',
        }} onClick={e => { if (e.target === e.currentTarget) setShowAdd(false) }}>
          <style>{`
            @keyframes modalFadeIn {
              from { opacity: 0; transform: scale(0.95) translateY(10px); }
              to { opacity: 1; transform: scale(1) translateY(0); }
            }
            @keyframes pulse {
              0% { box-shadow: 0 0 0 0 rgba(var(--pulse-color), 0.7); }
              70% { box-shadow: 0 0 0 6px rgba(var(--pulse-color), 0); }
              100% { box-shadow: 0 0 0 0 rgba(var(--pulse-color), 0); }
            }
          `}</style>
          <div style={{
            background: theme.cardBg, borderRadius: 16, padding: 32, width: 520,
            maxWidth: '90vw', boxShadow: theme.shadowHover, border: `1px solid ${theme.cardBorder}`,
          }}>
            <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>➕ 新增客户 / Add Client</h3>

            {/* Phone input with live check */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 6 }}>电话 / Phone</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{ position: 'relative', flex: 1 }}>
                  <span style={{ position: 'absolute', left: 12, top: 12, fontSize: 16, color: theme.textSecondary }}>📞</span>
                  <input
                    value={addPhone}
                    onChange={e => { setAddPhone(e.target.value); checkPhone(e.target.value) }}
                    placeholder="e.g. +60123456789"
                    style={{ ...modalInputStyle(theme), width: '100%', paddingLeft: 40, fontSize: 16, fontWeight: 600, padding: '12px 12px 12px 36px' }}
                  />
                </div>
                <button className="glass-btn" onClick={() => checkPhone(addPhone)} style={{ ...getBtnStyle(theme), padding: '0 16px' }}>
                  {t('clients.check_again', getLang()) || 'Check Again'}
                </button>
              </div>
              {phoneStatus && (
                <div style={{ marginTop: 8, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8,
                  padding: phoneStatus.status === 'taken' ? '10px 12px' : 0,
                  background: phoneStatus.status === 'taken' ? '#fee2e2' : 'transparent',
                  borderRadius: 6, border: phoneStatus.status === 'taken' ? '1px solid #f87171' : 'none'
                 }}>
                  {phoneStatus.status === 'available' && (
                    <>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#22c55e', '--pulse-color': '34, 197, 94' } as any} className="pulse-dot"></div>
                      <span className="pill-badge" style={{ color: '#15803d', background: '#dcfce7', fontWeight: 600, padding: '2px 8px', borderRadius: 12 }}>
                        {t('clients.phone_available', getLang()) || 'Available'}
                      </span>
                    </>
                  )}
                  {phoneStatus.status === 'own' && (
                    <>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b', '--pulse-color': '245, 158, 11' } as any} className="pulse-dot"></div>
                      <span className="pill-badge" style={{ color: '#b45309', background: '#fef3c7', fontWeight: 600, padding: '2px 8px', borderRadius: 12 }}>
                        {t('clients.phone_own', getLang()) || 'Your number (editable)'}
                      </span>
                    </>
                  )}
                  {phoneStatus.status === 'taken' && (
                    <>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', '--pulse-color': '239, 68, 68' } as any} className="pulse-dot"></div>
                      <span style={{ color: '#b91c1c', fontWeight: 600 }}>
                        {t('clients.phone_taken', getLang())?.replace('{owner}', phoneStatus.owner) || `Taken by ${phoneStatus.owner}`} ({phoneStatus.submitted_at?.split('T')[0]})
                      </span>
                    </>
                  )}
                </div>
              )}
              <style>{`.pulse-dot { animation: pulse 2s infinite; }`}</style>
            </div>

            {/* 2-column grid layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              {/* Source */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>来源 / Source</label>
                <select
                  value={addSource}
                  onChange={e => setAddSource(e.target.value)}
                  style={{ ...modalInputStyle(theme), width: '100%' }}
                >
                  {['web', 'telegram', 'whatsapp', 'referral', 'facebook', 'instagram', 'tiktok', 'other'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              {/* Platform */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>平台 / Platform</label>
                <select value={addPlatform} onChange={e => setAddPlatform(e.target.value)}
                  style={{ ...modalInputStyle(theme), width: '100%' }}>
                  <option value="">-- Select --</option>
                  {['MT5', 'MT4', 'cTrader', 'Other'].map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              {/* Nickname */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>昵称 / Nickname</label>
                <input value={addNickname} onChange={e => setAddNickname(e.target.value)}
                  placeholder="Optional" style={{ ...modalInputStyle(theme), width: '100%' }} />
              </div>

              {/* Account ID */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>编号 / Account ID</label>
                <input value={addAccountId} onChange={e => setAddAccountId(e.target.value)}
                  placeholder="Optional" style={{ ...modalInputStyle(theme), width: '100%' }} />
              </div>

              {/* Category */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>类别 / Category</label>
                <div style={{ position: 'relative' }}>
                  <select value={addCategory} onChange={e => setAddCategory(e.target.value)}
                    style={{ ...modalInputStyle(theme), width: '100%', appearance: 'none' }}>
                    <option value="">-- Select --</option>
                    {['UK表单粉', 'CA表单粉', 'AU表单粉', 'EU表单粉', 'US表单粉', 'SEA表单粉', 'Other'].map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  {addCategory && (
                    <span className="pill-badge" style={{
                      position: 'absolute', right: 30, top: '50%', transform: 'translateY(-50%)',
                      background: theme.accentLight, color: theme.accent, fontSize: 10, padding: '2px 6px', borderRadius: 4, pointerEvents: 'none'
                    }}>
                      {addCategory}
                    </span>
                  )}
                </div>
              </div>

              {/* Recruiter */}
              <div>
                <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>招聘人员 / Recruiter</label>
                <input value={addRecruiter} onChange={e => setAddRecruiter(e.target.value)}
                  placeholder="Optional" style={{ ...modalInputStyle(theme), width: '100%' }} />
              </div>
            </div>

            {addError && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 16, background: '#fee2e2', padding: 8, borderRadius: 6 }}>{addError}</div>}
            {addSuccess && <div style={{ color: '#22c55e', fontSize: 13, marginBottom: 16, background: '#dcfce7', padding: 8, borderRadius: 6 }}>{addSuccess}</div>}

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="glass-btn" onClick={() => setShowAdd(false)} style={{ ...getBtnStyle(theme), padding: '10px 24px', background: theme.bg }}>
                取消 / Cancel
              </button>
              <button
                className="glass-btn"
                onClick={submitNewClient}
                disabled={addSubmitting || phoneStatus?.status === 'taken'}
                style={{
                  ...getBtnStyle(theme), padding: '10px 24px',
                  background: phoneStatus?.status === 'taken' ? theme.cardBorder : theme.accent,
                  color: '#fff', border: 'none', fontWeight: 600,
                  opacity: addSubmitting || phoneStatus?.status === 'taken' ? 0.6 : 1,
                }}
              >
                {addSubmitting ? '...' : '提交 / Submit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const modalInputStyle = (theme: any): React.CSSProperties => ({
  padding: '10px 12px',
  background: theme.inputBg,
  border: `1px solid ${theme.inputBorder}`,
  borderRadius: 8,
  color: theme.textPrimary,
  fontSize: 14,
  outline: 'none',
  boxSizing: 'border-box' as const,
  transition: 'border-color 0.2s',
})

const getInputStyle = (theme: any): React.CSSProperties => ({
  padding: '10px 16px',
  background: theme.inputBg,
  border: `1px solid ${theme.inputBorder}`,
  borderRadius: 8,
  color: theme.textPrimary,
  fontSize: 14,
  outline: 'none',
  minWidth: 240,
  boxShadow: theme.shadow,
  transition: 'all 0.2s',
})

const getBtnStyle = (theme: any): React.CSSProperties => ({
  padding: '10px 20px',
  background: theme.cardBg,
  border: `1px solid ${theme.cardBorder}`,
  borderRadius: 8,
  color: theme.textPrimary,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  boxShadow: theme.shadow,
  transition: 'all 0.2s',
})
