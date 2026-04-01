import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Client, FunnelStage } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from './Dashboard'
import { useTheme } from '../ThemeContext'

export default function Pipeline() {
  const { theme } = useTheme()
  const [funnel, setFunnel] = useState<FunnelStage[]>([])
  const [pipeline, setPipeline] = useState<Record<string, Client[]>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => {
    Promise.all([api.funnel(), api.pipeline()])
      .then(([f, p]) => {
        setFunnel(f)
        setPipeline(p)
        if (f.length > 0) setSelected(f[0].stage)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const selectedClients = selected ? pipeline[selected] || [] : []

  return (
    <div>
      <PageHeader title="漏斗管道" />

      {/* Funnel stages */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${funnel.length}, 1fr)`,
          gap: 8,
          marginBottom: 24,
        }}
      >
        {funnel.map(stage => (
          <button
            key={stage.stage}
            onClick={() => setSelected(stage.stage)}
            style={{
              background: selected === stage.stage ? '${theme.cardBorder}' : theme.cardBg,
              border: `2px solid ${selected === stage.stage ? STATUS_COLORS[stage.stage] || '#0f3460' : theme.cardBorder}`,
              borderRadius: 8,
              padding: '16px 12px',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'all 0.15s',
            }}
          >
            <div style={{ fontSize: 24, fontWeight: 700, color: STATUS_COLORS[stage.stage] || '${theme.textPrimary}' }}>
              {stage.count}
            </div>
            <div style={{ fontSize: 12, color: theme.textPrimary, marginTop: 4 }}>
              {STATUS_LABELS[stage.stage] || stage.stage}
            </div>
            <div style={{ fontSize: 11, color: theme.textSecondary, marginTop: 2 }}>{stage.pct}%</div>
          </button>
        ))}
      </div>

      {/* Filtered client list */}
      {selected && (
        <div
          style={{
            background: theme.cardBg,
            border: `1px solid ${theme.cardBorder}`,
            borderRadius: 8,
            padding: 20,
          }}
        >
          <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {STATUS_LABELS[selected] || selected} — {selectedClients.length} 个客户
          </div>
          {selectedClients.length === 0 ? (
            <Empty />
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${theme.cardBorder}` }}>
                  {['电话', '来源', '负责人', '团队', '存款', '创建时间'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: theme.textSecondary, fontWeight: 600 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {selectedClients.map(c => (
                  <tr
                    key={c.id}
                    onClick={() => nav(`/clients/${c.id}`)}
                    style={{ borderBottom: `1px solid ${theme.cardBorder}30`, cursor: 'pointer' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '${theme.cardBorder}30')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '10px 12px', color: '#74b9ff', fontFamily: 'monospace' }}>
                      {c.phone}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#aaa' }}>{c.source || '-'}</td>
                    <td style={{ padding: '10px 12px' }}>{c.frontdesk_name || '-'}</td>
                    <td style={{ padding: '10px 12px', color: theme.textSecondary }}>{c.team || '-'}</td>
                    <td style={{ padding: '10px 12px', color: c.total_deposited > 0 ? '${theme.accent}' : theme.textSecondary }}>
                      {c.total_deposited > 0 ? `$${c.total_deposited.toFixed(0)}` : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', color: theme.textSecondary, fontSize: 12 }}>
                      {c.created_at ? new Date(c.created_at).toLocaleDateString('zh') : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
