import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { Client, ClientList } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from './Dashboard'

const STATUSES = ['', 'new', 'contacted', 'replied', 'registered', 'training', 'ordered', 'withdrew', 'ghosted', 'dead']
const PER_PAGE = 50

export default function Clients() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<ClientList | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

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
          style={inputStyle}
        />
        <select
          value={status}
          onChange={e => setParam('status', e.target.value)}
          style={{ ...inputStyle, width: 160 }}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s ? STATUS_LABELS[s] || s : '全部状态'}
            </option>
          ))}
        </select>
        <button
          onClick={() => api.exportClients(status || undefined, undefined).catch(console.error)}
          style={btnStyle}
        >
          导出 CSV
        </button>
        {data && (
          <span style={{ fontSize: 12, color: '#7f848e', marginLeft: 'auto' }}>
            共 {data.total} 条记录
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <Spinner />
      ) : (
        <div style={{ background: '#16213e', border: '1px solid #0f3460', borderRadius: 8 }}>
          {!data || data.clients.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty />
            </div>
          ) : (
            <>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #0f3460' }}>
                    {['电话', '状态', '来源', '负责人', '团队', '存款', '下次跟进', '创建时间'].map(h => (
                      <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: '#7f848e', fontWeight: 600 }}>
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
                      style={{ borderBottom: '1px solid #0f346025', cursor: 'pointer', transition: 'background 0.1s' }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#0f346030')}
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
                            color: STATUS_COLORS[c.status] || '#7f848e',
                            fontWeight: 600,
                          }}
                        >
                          {STATUS_LABELS[c.status] || c.status}
                        </span>
                      </td>
                      <td style={{ padding: '10px 14px', color: '#aaa' }}>{c.source || '-'}</td>
                      <td style={{ padding: '10px 14px' }}>{c.frontdesk_name || '-'}</td>
                      <td style={{ padding: '10px 14px', color: '#7f848e' }}>{c.team || '-'}</td>
                      <td style={{ padding: '10px 14px', color: c.total_deposited > 0 ? '#00b894' : '#7f848e' }}>
                        {c.total_deposited > 0 ? `$${c.total_deposited.toFixed(0)}` : '-'}
                      </td>
                      <td style={{ padding: '10px 14px', color: c.next_followup ? '#fdcb6e' : '#7f848e', fontSize: 12 }}>
                        {c.next_followup ? new Date(c.next_followup).toLocaleDateString('zh') : '-'}
                      </td>
                      <td style={{ padding: '10px 14px', color: '#7f848e', fontSize: 12 }}>
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
                    borderTop: '1px solid #0f3460',
                    alignItems: 'center',
                  }}
                >
                  <button
                    onClick={() => setParam('page', String(page - 1))}
                    disabled={page <= 1}
                    style={{ ...btnStyle, opacity: page <= 1 ? 0.4 : 1 }}
                  >
                    上一页
                  </button>
                  <span style={{ fontSize: 12, color: '#7f848e' }}>
                    第 {page} / {totalPages} 页
                  </span>
                  <button
                    onClick={() => setParam('page', String(page + 1))}
                    disabled={page >= totalPages}
                    style={{ ...btnStyle, opacity: page >= totalPages ? 0.4 : 1 }}
                  >
                    下一页
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  padding: '8px 12px',
  background: '#16213e',
  border: '1px solid #0f3460',
  borderRadius: 4,
  color: '#e0e0e0',
  fontSize: 13,
  outline: 'none',
  minWidth: 200,
}

const btnStyle: React.CSSProperties = {
  padding: '8px 16px',
  background: '#0f3460',
  border: '1px solid #0f3460',
  borderRadius: 4,
  color: '#e0e0e0',
  fontSize: 12,
  cursor: 'pointer',
}
