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
      <PageHeader title="Funnel Pipeline" sub="Visualize and manage your sales pipeline stages." />

      {/* Funnel stages */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(auto-fit, minmax(120px, 1fr))`,
          gap: 16,
          marginBottom: 32,
        }}
      >
        {funnel.map(stage => {
          const isSelected = selected === stage.stage;
          const color = STATUS_COLORS[stage.stage] || theme.textSecondary;
          return (
            <button className="glass-btn"
              key={stage.stage}
              onClick={() => setSelected(stage.stage)}
              style={{
                background: isSelected ? theme.cardBg : theme.bg,
                border: `1px solid ${isSelected ? color : theme.cardBorder}`,
                borderRadius: 16,
                padding: '24px 16px',
                cursor: 'pointer',
                textAlign: 'center',
                transition: 'all 0.3s ease',
                boxShadow: isSelected ? `0 4px 12px ${color}30` : theme.shadow,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                transform: isSelected ? 'translateY(-2px)' : 'none',
              }}
              onMouseOver={e => { if (!isSelected) e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseOut={e => { if (!isSelected) e.currentTarget.style.transform = 'none'; }}
            >
              <div style={{ fontSize: 36, fontWeight: 700, color: color, letterSpacing: '-0.03em', marginBottom: 12 }}>
                {stage.count}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                {STATUS_LABELS[stage.stage] || stage.stage}
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginTop: 8, background: `${color}15`, padding: '4px 12px', borderRadius: 9999 }}>
                {stage.pct}%
              </div>
            </button>
          )
        })}
      </div>

      {/* Filtered client list */}
      {selected && (
        <div
          style={{
            background: theme.cardBg,
            border: `1px solid ${theme.cardBorder}`,
            borderRadius: 12,
            padding: 32,
            boxShadow: theme.shadow,
          }}
        >
          <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary, marginBottom: 24, textTransform: 'uppercase', letterSpacing: 0.5, display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: STATUS_COLORS[selected] || theme.textSecondary, boxShadow: `0 0 0 4px ${STATUS_COLORS[selected] || theme.textSecondary}30` }}></div>
            {STATUS_LABELS[selected] || selected} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({selectedClients.length} clients)</span>
          </div>
          {selectedClients.length === 0 ? (
            <Empty />
          ) : (
            <div style={{ overflowX: 'auto', borderRadius: 12, border: `1px solid ${theme.cardBorder}`, boxShadow: theme.shadow }}>
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
                    {['Phone', 'Source', 'Owner', 'Team', 'Deposit', 'Created At'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {selectedClients.map((c, i) => (
                    <tr className="data-grid-row"
                      key={c.id}
                      onClick={() => nav(`/clients/${c.id}`)}
                    >
                      <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                        {c.phone}
                      </td>
                      <td style={{ color: theme.textSecondary, fontWeight: 500 }}>{c.source || '—'}</td>
                      <td style={{ fontWeight: 500 }}>{c.frontdesk_name || '—'}</td>
                      <td style={{ color: theme.textSecondary, fontWeight: 500 }}>{c.team || '—'}</td>
                      <td style={{ fontFamily: 'monospace', color: c.total_deposited > 0 ? theme.success : theme.textSecondary, fontWeight: c.total_deposited > 0 ? 700 : 500 }}>
                        {c.total_deposited > 0 ? `$${c.total_deposited.toLocaleString()}` : '—'}
                      </td>
                      <td style={{ fontFamily: 'monospace', color: theme.textSecondary, fontSize: 12, fontWeight: 500 }}>
                        {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
