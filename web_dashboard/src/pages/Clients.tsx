import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { Client, ClientList } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from './Dashboard'
import { useTheme } from '../ThemeContext'

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
      const res = await api.createClient({ phone: addPhone.trim(), source: addSource, nickname: addNickname || undefined })
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
      <PageHeader title="客户列表" />

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="搜索电话/来源..."
          value={search}
          onChange={e => setParam('search', e.target.value)}
          style={getInputStyle(theme)}
        />
        <select
          value={status}
          onChange={e => setParam('status', e.target.value)}
          style={{ ...getInputStyle(theme), width: 160 }}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s ? STATUS_LABELS[s] || s : '全部状态'}
            </option>
          ))}
        </select>
        <button
          onClick={() => api.exportClients(status || undefined, undefined).catch(console.error)}
          style={getBtnStyle(theme)}
        >
          导出 CSV
        </button>
        <button
          onClick={() => { setShowAdd(true); setAddError(''); setAddSuccess(''); setPhoneStatus(null) }}
          style={{ ...getBtnStyle(theme), background: '#22c55e', color: '#fff', border: 'none', fontWeight: 600 }}
        >
          ➕ 新增客户
        </button>
        {data && (
          <span style={{ fontSize: 12, color: theme.textSecondary, marginLeft: 'auto' }}>
            共 {data.total} 条记录
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <Spinner />
      ) : (
        <div style={{ background: theme.cardBg, border: `1px solid ${theme.cardBorder}`, borderRadius: 8 }}>
          {!data || data.clients.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty />
            </div>
          ) : (
            <>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${theme.cardBorder}` }}>
                    {['电话', '状态', '来源', '负责人', '团队', '存款', '下次跟进', '创建时间'].map(h => (
                      <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: theme.textSecondary, fontWeight: 600 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.clients.map((c: Client) => (
                    <tr
                      key={c.id}
                      onClick={() => nav(`/clients/${c.id}`)}
                      style={{ borderBottom: `1px solid ${theme.cardBorder}25`, cursor: 'pointer', transition: 'background 0.1s' }}
                      onMouseEnter={e => (e.currentTarget.style.background = '${theme.cardBorder}30')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td style={{ padding: '10px 14px', color: '#74b9ff', fontFamily: 'monospace', fontSize: 12 }}>
                        {c.phone}
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        <span
                          style={{
                            padding: '2px 8px',
                            borderRadius: 3,
                            fontSize: 11,
                            background: `${STATUS_COLORS[c.status] || '#7f848e'}30`,
                            color: STATUS_COLORS[c.status] || '${theme.textSecondary}',
                            fontWeight: 600,
                          }}
                        >
                          {STATUS_LABELS[c.status] || c.status}
                        </span>
                      </td>
                      <td style={{ padding: '10px 14px', color: '#aaa' }}>{c.source || '-'}</td>
                      <td style={{ padding: '10px 14px' }}>{c.frontdesk_name || '-'}</td>
                      <td style={{ padding: '10px 14px', color: theme.textSecondary }}>{c.team || '-'}</td>
                      <td style={{ padding: '10px 14px', color: c.total_deposited > 0 ? '${theme.accent}' : theme.textSecondary }}>
                        {c.total_deposited > 0 ? `$${c.total_deposited.toFixed(0)}` : '-'}
                      </td>
                      <td style={{ padding: '10px 14px', color: c.next_followup ? '${theme.chartLine}' : theme.textSecondary, fontSize: 12 }}>
                        {c.next_followup ? new Date(c.next_followup).toLocaleDateString('zh') : '-'}
                      </td>
                      <td style={{ padding: '10px 14px', color: theme.textSecondary, fontSize: 12 }}>
                        {c.created_at ? new Date(c.created_at).toLocaleDateString('zh') : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div
                  style={{
                    display: 'flex',
                    gap: 8,
                    padding: '14px 16px',
                    borderTop: `1px solid ${theme.cardBorder}`,
                    alignItems: 'center',
                  }}
                >
                  <button
                    onClick={() => setParam('page', String(page - 1))}
                    disabled={page <= 1}
                    style={{ ...getBtnStyle(theme), opacity: page <= 1 ? 0.4 : 1 }}
                  >
                    上一页
                  </button>
                  <span style={{ fontSize: 12, color: theme.textSecondary }}>
                    第 {page} / {totalPages} 页
                  </span>
                  <button
                    onClick={() => setParam('page', String(page + 1))}
                    disabled={page >= totalPages}
                    style={{ ...getBtnStyle(theme), opacity: page >= totalPages ? 0.4 : 1 }}
                  >
                    下一页
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
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={e => { if (e.target === e.currentTarget) setShowAdd(false) }}>
          <div style={{
            background: theme.cardBg, borderRadius: 12, padding: 24, width: 420,
            maxWidth: '90vw', boxShadow: theme.shadow,
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>➕ 新增客户 / Add Client</h3>

            {/* Phone input with live check */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>电话 / Phone</label>
              <input
                value={addPhone}
                onChange={e => { setAddPhone(e.target.value); checkPhone(e.target.value) }}
                placeholder="e.g. +60123456789"
                style={{ ...modalInputStyle(theme), width: '100%' }}
              />
              {phoneStatus && (
                <div style={{ marginTop: 6, fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {phoneStatus.status === 'available' && (
                    <span style={{ color: '#22c55e', fontWeight: 600 }}>✓ 可用 / Available</span>
                  )}
                  {phoneStatus.status === 'own' && (
                    <span style={{ color: '#f59e0b', fontWeight: 600 }}>⚡ 你的号码 / Your Number — editable</span>
                  )}
                  {phoneStatus.status === 'taken' && (
                    <span style={{ color: '#ef4444', fontWeight: 600 }}>
                      ✗ 已被占用 / Taken by {phoneStatus.owner} ({phoneStatus.submitted_at?.split('T')[0]})
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Source */}
            <div style={{ marginBottom: 12 }}>
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

            {/* Nickname */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, color: theme.textSecondary, display: 'block', marginBottom: 4 }}>昵称 / Nickname (optional)</label>
              <input
                value={addNickname}
                onChange={e => setAddNickname(e.target.value)}
                placeholder="Optional"
                style={{ ...modalInputStyle(theme), width: '100%' }}
              />
            </div>

            {addError && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 10 }}>{addError}</div>}
            {addSuccess && <div style={{ color: '#22c55e', fontSize: 12, marginBottom: 10 }}>{addSuccess}</div>}

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowAdd(false)} style={{ ...getBtnStyle(theme), padding: '8px 20px' }}>
                取消 / Cancel
              </button>
              <button
                onClick={submitNewClient}
                disabled={addSubmitting || phoneStatus?.status === 'taken'}
                style={{
                  ...getBtnStyle(theme), padding: '8px 20px',
                  background: phoneStatus?.status === 'taken' ? '#94a3b8' : '#22c55e',
                  color: '#fff', border: 'none', fontWeight: 600,
                  opacity: addSubmitting ? 0.6 : 1,
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
  padding: '8px 12px',
  background: theme.inputBg,
  border: `1px solid ${theme.inputBorder}`,
  borderRadius: 6,
  color: theme.textPrimary,
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box' as const,
})

const getInputStyle = (theme: any): React.CSSProperties => ({
  padding: '8px 12px',
  background: theme.cardBg,
  border: `1px solid ${theme.cardBorder}`,
  borderRadius: 4,
  color: theme.textPrimary,
  fontSize: 13,
  outline: 'none',
  minWidth: 200,
})

const getBtnStyle = (theme: any): React.CSSProperties => ({
  padding: '8px 16px',
  background: theme.cardBorder,
  border: `1px solid ${theme.cardBorder}`,
  borderRadius: 4,
  color: theme.textPrimary,
  fontSize: 12,
  cursor: 'pointer',
})
