import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Client, FunnelStage } from '../types'
import { STATUS_COLORS, STATUS_LABELS } from '../types'
import { Empty, PageHeader, Spinner } from '../components/SharedUI'
import { DataGrid, formatPhone, Column } from '../components/DataGrid'
import { useTheme } from '../ThemeContext'
import { t, getLang } from '../i18n'

export default function Pipeline() {
  const { theme } = useTheme()
  const [error, setError] = useState('');
  const lang = getLang()
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
      .catch(e => { console.error(e); setError(t('common.update_failed', lang as any)); })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  const selectedClients = selected ? pipeline[selected] || [] : []

  return (
    <div className="page-container">
      <PageHeader title={t('pipeline.title', lang)} sub={t('pipeline.description', lang)} />

      {error && <div className="alert alert-error">{error}</div>}

      {/* Funnel stages */}
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(120px, 1fr))`, gap: 12, marginBottom: 20 }}>
        {funnel.map(stage => {
          const isSelected = selected === stage.stage;
          const color = STATUS_COLORS[stage.stage] || theme.textSecondary;
          return (
            <button
              className="card"
              key={stage.stage}
              onClick={() => setSelected(stage.stage)}
              style={{
                cursor: 'pointer',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                border: `1px solid ${isSelected ? color : 'var(--card-border)'}`,
                boxShadow: isSelected ? `0 4px 12px ${color}30` : undefined,
                transform: isSelected ? 'translateY(-2px)' : undefined,
              }}
            >
              <div className="metric-value" style={{ color: color, marginBottom: 8 }}>
                {stage.count}
              </div>
              <div className="metric-label" style={{ color: theme.textPrimary }}>
                {STATUS_LABELS[stage.stage] || stage.stage}
              </div>
              <span className="pill-badge" style={{ marginTop: 8, background: `${color}15`, color: color, fontSize: 12 }}>
                {stage.pct}%
              </span>
            </button>
          )
        })}
      </div>

      {/* Filtered client list */}
      {selected && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 12, height: 12, borderRadius: 12, background: STATUS_COLORS[selected] || theme.textSecondary, boxShadow: `0 0 0 4px ${STATUS_COLORS[selected] || theme.textSecondary}30` }} />
            {STATUS_LABELS[selected] || selected} <span style={{ color: theme.textMuted, fontWeight: 500 }}>({selectedClients.length} {t('org.members', lang)})</span>
          </div>
          {selectedClients.length === 0 ? (
            <Empty />
          ) : (() => {
            const columns: Column<Client>[] = [
                { key: 'phone', label: t('clients.phone', lang), monospace: true, render: c => formatPhone(c.phone) },
                { key: 'source', label: t('clients.source', lang), render: c => <span style={{color: theme.textSecondary}}>{c.source || '—'}</span> },
                { key: 'frontdesk', label: t('clients.owner', lang), render: c => c.frontdesk_name || '—' },
                { key: 'team', label: t('detail.team', lang), render: c => <span style={{color: theme.textSecondary}}>{c.team || '—'}</span> },
                { key: 'deposit', label: t('clients.deposit', lang), monospace: true, render: c => c.total_deposited > 0 ? <span style={{color: theme.success}}>${c.total_deposited.toLocaleString()}</span> : <span style={{color: theme.textSecondary}}>—</span> },
                { key: 'created_at', label: t('clients.created_at', lang), monospace: true, render: c => <span style={{color: theme.textSecondary, fontSize: 12}}>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</span> }
            ]
            return <DataGrid columns={columns} data={selectedClients} onRowClick={c => nav(`/clients/${c.id}`)} />
          })()}
        </div>
      )}
    </div>
  )
}
