import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import type { ClientDetail as TClientDetail } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { PageHeader, Spinner } from './Dashboard'

const CARD: React.CSSProperties = {
  background: '#16213e',
  border: '1px solid #0f3460',
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
}

function Field({ label, value, accent }: { label: string; value: string | number | null | undefined; accent?: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: '#7f848e', marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: accent || '#e0e0e0' }}>{value || '-'}</div>
    </div>
  )
}

export default function ClientDetail() {
  const { id } = useParams<{ id: string }>()
  const [client, setClient] = useState<TClientDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    if (!id) return
    api.clientDetail(parseInt(id, 10))
      .then(setClient)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <Spinner />
  if (error) return <div style={{ color: '#ff7675', padding: 20 }}>{error}</div>
  if (!client) return null

  const statusColor = STATUS_COLORS[client.status] || '#7f848e'
  const totalDeposits = client.deposits.reduce((s, d) => s + d.amount, 0)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button
          onClick={() => nav(-1)}
          style={{
            background: 'transparent',
            border: '1px solid #0f3460',
            color: '#7f848e',
            padding: '6px 12px',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          ← 返回
        </button>
        <PageHeader title={client.phone} />
        <span
          style={{
            padding: '4px 12px',
            borderRadius: 4,
            background: `${statusColor}25`,
            color: statusColor,
            fontSize: 13,
            fontWeight: 600,
            marginLeft: 8,
          }}
        >
          {STATUS_LABELS[client.status] || client.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Client info */}
        <div style={CARD}>
          <div style={{ fontSize: 12, color: '#7f848e', marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            客户信息
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Field label="电话" value={client.phone} accent="#74b9ff" />
            <Field label="来源" value={client.source} />
            <Field label="负责人" value={client.frontdesk_name} />
            <Field label="团队" value={client.team} />
            <Field label="总存款" value={totalDeposits > 0 ? `$${totalDeposits.toFixed(2)}` : null} accent="#00b894" />
            <Field label="创建时间" value={client.created_at ? new Date(client.created_at).toLocaleDateString('zh') : null} />
          </div>

          {/* Milestone timeline */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: '#7f848e', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              里程碑
            </div>
            {[
              { label: '联系时间', val: client.contacted_at },
              { label: '回复时间', val: client.replied_at },
              { label: '注册时间', val: client.registered_at },
              { label: '培训时间', val: client.training_at },
              { label: '首次下单', val: client.first_order_at },
            ].map(m => m.val && (
              <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #0f346025', fontSize: 13 }}>
                <span style={{ color: '#7f848e' }}>{m.label}</span>
                <span style={{ color: '#e0e0e0' }}>{new Date(m.val).toLocaleString('zh')}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Deposits */}
        <div style={CARD}>
          <div style={{ fontSize: 12, color: '#7f848e', marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            存款记录
          </div>
          {client.deposits.length === 0 ? (
            <div style={{ color: '#7f848e', fontSize: 13 }}>无存款记录</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #0f3460' }}>
                  {['金额', '平台', '日期'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: '#7f848e', fontWeight: 600 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {client.deposits.map(d => (
                  <tr key={d.id} style={{ borderBottom: '1px solid #0f346025' }}>
                    <td style={{ padding: '8px 10px', color: '#00b894', fontWeight: 600 }}>
                      ${d.amount.toFixed(2)} {d.currency}
                    </td>
                    <td style={{ padding: '8px 10px', color: '#aaa' }}>{d.platform || '-'}</td>
                    <td style={{ padding: '8px 10px', color: '#7f848e', fontSize: 12 }}>
                      {d.deposit_date ? new Date(d.deposit_date).toLocaleDateString('zh') : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Notes timeline */}
      <div style={CARD}>
        <div style={{ fontSize: 12, color: '#7f848e', marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          互动记录 ({client.notes.length})
        </div>
        {client.notes.length === 0 ? (
          <div style={{ color: '#7f848e', fontSize: 13 }}>无记录</div>
        ) : (
          <div>
            {client.notes.map((n, i) => (
              <div
                key={n.id}
                style={{
                  display: 'flex',
                  gap: 14,
                  paddingBottom: i < client.notes.length - 1 ? 16 : 0,
                  marginBottom: i < client.notes.length - 1 ? 16 : 0,
                  borderBottom: i < client.notes.length - 1 ? '1px solid #0f346025' : 'none',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20, flexShrink: 0 }}>
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: n.note_type === 'status_change' ? '#00b894' : '#0f3460',
                      border: '2px solid #16213e',
                      flexShrink: 0,
                    }}
                  />
                  {i < client.notes.length - 1 && (
                    <div style={{ flex: 1, width: 1, background: '#0f3460', marginTop: 4 }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: '#7f848e' }}>
                      {n.staff_name || '系统'}
                      {n.note_type === 'status_change' && n.old_status && n.new_status && (
                        <span style={{ marginLeft: 8 }}>
                          <span style={{ color: STATUS_COLORS[n.old_status] || '#7f848e' }}>
                            {STATUS_LABELS[n.old_status] || n.old_status}
                          </span>
                          <span style={{ color: '#7f848e' }}> → </span>
                          <span style={{ color: STATUS_COLORS[n.new_status] || '#e0e0e0' }}>
                            {STATUS_LABELS[n.new_status] || n.new_status}
                          </span>
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: 11, color: '#7f848e' }}>
                      {n.created_at ? new Date(n.created_at).toLocaleString('zh') : ''}
                    </span>
                  </div>
                  {n.content && (
                    <div style={{ fontSize: 13, color: '#e0e0e0', lineHeight: 1.5 }}>{n.content}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
